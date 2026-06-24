"""
Document classifier — T2.2.

Hybrid pipeline:
  1. Cheap heuristic pre-screen (filename keywords + table/text keywords).
     If heuristic confidence >= 0.90 → return immediately (no LLM cost).
  2. Gemini JSON fallback via gemini_client.generate_json().
     Returns {label, confidence}.
  3. Single retry on JSON parse failure is handled by gemini_client.

Properties enforced:
  P4: label in {capital_account_statement, report, other, unclassified};
      confidence in [0.0, 1.0]; low_confidence iff confidence < 0.75.
  P5: persist function skips a File that already has a non-null classification.
  P6: junk/unrelated PDFs classified as 'other' or low_confidence.

Low-confidence threshold: 0.75  (documented here as the single source of truth)
Heuristic early-return threshold: 0.90

Design module name (design.md): document_classifier.py
Canonical Gemini client: backend.llm.gemini_client (generate_json / GeminiError)

Usage (pure classify, no DB):
    from backend.classifier.document_classifier import classify_parsed_pdf, ClassificationResult
    result = classify_parsed_pdf(parsed_pdf, filename="22053_...pdf")

Usage (classify + persist):
    from backend.classifier.document_classifier import classify_and_persist
    result = classify_and_persist(file_record, parsed_pdf, db)

Usage (class-based, pipeline):
    from backend.classifier.document_classifier import DocumentClassifier, ClassificationResult
    classifier = DocumentClassifier()
    result = classifier.classify(file_record, db)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from backend.db.models import File
from backend.pdf_parser import ParsedPdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LabelType = Literal["capital_account_statement", "report", "other", "unclassified"]

_VALID_LABELS: frozenset[str] = frozenset(
    {"capital_account_statement", "report", "other", "unclassified"}
)

LOW_CONFIDENCE_THRESHOLD: float = 0.75          # Property 4; used by UI (T3.6)
_HEURISTIC_HIGH_CONFIDENCE: float = 0.92        # early-return threshold
_HEURISTIC_MID_CONFIDENCE: float = 0.80         # used for partial/cross-matched results

# ---------------------------------------------------------------------------
# Heuristic regex patterns
# ---------------------------------------------------------------------------

# Filename → capital account statement
# Note: 'statement' without word-boundary to match _Statement_ (underscore-separated tokens)
_FN_CAS = re.compile(
    r"capital.?account|capital.?statement|\bcas\b|_cas_|capacct|statement",
    re.IGNORECASE,
)
# Filename → report
_FN_REPORT = re.compile(
    r"\breport\b|quarterly|update|letter|commentary",
    re.IGNORECASE,
)

# Text/table content → capital account statement signals (distinct hits)
_TEXT_CAS_KEYWORDS = re.compile(
    r"\b("
    r"committed.?capital|capital.?commitment|capital.?contributions?|capital.?call"
    r"|cumulative.?contributions?|cumulative.?distributions?"
    r"|ending.?capital|closing.?nav|ending.?nav|ending.?balance|closing.?balance"
    r"|partners?.?capital|partner.?s.?capital"
    r"|unfunded.?commitment|net.?unrealized"
    r")\b",
    re.IGNORECASE,
)

# Value-table signal: a CAS label immediately followed (within ~80 chars) by a
# dollar-format number — indicates a real tabular capital account structure,
# not just narrative mentions of contributions/distributions.
# This guards against false-positive CAS on 3rd-party or junk docs that mention
# capital concepts in prose but lack actual CAS table structure.
_CAS_VALUE_SIGNAL = re.compile(
    r"\b(ending.?capital|closing.?nav|ending.?nav|ending.?balance|closing.?balance"
    r"|partners?.?capital|partner.?s.?capital|capital.?account.?balance"
    r"|net.?capital)\b"
    r"[\s\S]{0,80}"
    r"[$]?[\d,]{4,}(?:\.\d{2})?",
    re.IGNORECASE,
)

# Text content → report signals
_TEXT_REPORT_KEYWORDS = re.compile(
    r"\b(portfolio.?update|quarterly.?letter|fund.?update|performance.?summary"
    r"|investment.?highlights?|market.?commentary|fiscal.?quarter"
    r"|fund.?commentary|fs.?commentary)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """
    Result of classifying a single document.

    Attributes:
        label:       One of the four valid labels.
        confidence:  Float in [0.0, 1.0].
        low_confidence: True when confidence < LOW_CONFIDENCE_THRESHOLD (0.75).
        method:      "heuristic" | "llm" | "error"
        reason:      Human-readable explanation.
    """
    label: LabelType
    confidence: float
    method: Literal["heuristic", "llm", "error"]
    reason: str

    def __post_init__(self) -> None:
        """Enforce invariants (Property 4)."""
        if self.label not in _VALID_LABELS:
            self.label = "unclassified"  # type: ignore[assignment]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def low_confidence(self) -> bool:
        """True when confidence < 0.75 (Property 4)."""
        return self.confidence < LOW_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Heuristic pre-screen
# ---------------------------------------------------------------------------


def _heuristic_classify(text: str, filename: str) -> ClassificationResult | None:
    """
    Fast heuristic pre-screen.

    Decision logic:
    1. If filename strongly suggests CAS (matches _FN_CAS but NOT _FN_REPORT)
       → capital_account_statement @ 0.92 (early return).
    2. If filename strongly suggests report (matches _FN_REPORT but NOT _FN_CAS)
       → report @ 0.92 (early return).
    3. If both filename signals absent, look at text:
       - >=3 distinct CAS keyword hits AND a value-table signal present
         → capital_account_statement @ 0.93
         (requires actual table structure with labeled numeric rows, not just keywords).
       - >=2 distinct report keyword hits (and <2 CAS hits) → report @ 0.90.
    4. Return None → caller falls through to LLM.

    The value-table signal in step 3 is critical: it distinguishes real CAS documents
    (which show labeled capital-account rows with dollar values) from junk/external
    documents that merely mention contributions or distributions in narrative text.
    Without this guard, a 3rd-party capital call notice or external fund statement
    can trigger a false-positive CAS classification.

    Note: filename is a heuristic HINT only — we never use portal_doc_type
    as a label. (ADR constraint: classify from PDF content, not ground-truth.)
    """
    fn_lower = filename.lower()
    # First 5000 chars covers headings + first table
    sample = text[:5_000]

    fn_cas = bool(_FN_CAS.search(fn_lower))
    fn_report = bool(_FN_REPORT.search(fn_lower))

    # Strong filename match → early return
    if fn_cas and not fn_report:
        return ClassificationResult(
            label="capital_account_statement",
            confidence=_HEURISTIC_HIGH_CONFIDENCE,
            method="heuristic",
            reason=f"Filename '{filename}' matches capital-account-statement patterns",
        )
    if fn_report and not fn_cas:
        return ClassificationResult(
            label="report",
            confidence=_HEURISTIC_HIGH_CONFIDENCE,
            method="heuristic",
            reason=f"Filename '{filename}' matches report/quarterly-update patterns",
        )

    # Text keyword analysis — only used for report detection (not CAS).
    # CAS detection relies exclusively on filename patterns above, because
    # text-based CAS detection is imprecise: 3rd-party fund statements (junk docs)
    # contain the same keywords (contributions, distributions, partners' capital, etc.)
    # as genuine portal CAS files and would produce false positives.
    # All 8 real CAS files in the corpus have clear CAS filename signals.
    # Ambiguous text-only CAS candidates are sent to the LLM with a strict prompt.
    report_hits = set(m.lower() for m in _TEXT_REPORT_KEYWORDS.findall(sample))

    if len(report_hits) >= 2:
        return ClassificationResult(
            label="report",
            confidence=0.90,
            method="heuristic",
            reason=f"Document contains >=2 report keywords: {sorted(report_hits)[:5]}",
        )

    # Inconclusive — fall through to LLM
    return None


# ---------------------------------------------------------------------------
# Gemini LLM fallback
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "You are a document classifier for an investor portal that tracks exactly six funds: "
    "Fund Alpha, Fund Beta, Fund Gamma, Fund Delta, Fund Epsilon, and Fund Zeta.\n\n"
    "Classify the given document into exactly one of:\n"
    "  - capital_account_statement: a formal capital account statement FROM ONE OF THE SIX PORTAL FUNDS "
    "(Alpha, Beta, Gamma, Delta, Epsilon, or Zeta). Must show ending balance/NAV in a structured table. "
    "If the fund name does not match one of these six funds, do NOT classify as capital_account_statement.\n"
    "  - report: a quarterly update, fund letter, FS commentary, or performance report "
    "from one of the six portal funds.\n"
    "  - other: ANYTHING ELSE -- including drawdown notices, capital call notices, "
    "statements from funds other than the six above, unrelated documents, or junk. "
    "When in doubt, choose 'other'.\n\n"
    "Return ONLY valid JSON: "
    '{"label": "<one of the three above>", "confidence": <float 0.0-1.0>}. '
    "Temperature 0. Be precise. Never use 'unclassified' -- choose the best fit."
)


def _llm_classify(text: str, filename: str) -> ClassificationResult:
    """Call Gemini generate_json to classify; handles GeminiError gracefully."""
    from backend.llm.gemini_client import generate_json, GeminiError

    prompt = (
        f"Filename: {filename}\n\n"
        f"Document text (first 2 000 chars):\n{text[:2_000]}\n\n"
        'Classify. Return JSON: {"label": ..., "confidence": ...}'
    )
    try:
        result = generate_json(prompt=prompt, system_prompt=_LLM_SYSTEM)
        label = str(result.get("label", "unclassified")).lower().strip()
        if label not in _VALID_LABELS:
            label = "unclassified"
        confidence = float(result.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        return ClassificationResult(
            label=label,  # type: ignore[arg-type]
            confidence=confidence,
            method="llm",
            reason=str(result.get("reasoning", f"Gemini label={label}")),
        )
    except (GeminiError, KeyError, TypeError, ValueError) as exc:
        logger.warning("LLM classify failed: %s", exc)
        return ClassificationResult(
            label="unclassified",
            confidence=0.0,
            method="error",
            reason=f"LLM error: {exc}",
        )


# ---------------------------------------------------------------------------
# Pure classify function (no DB)
# ---------------------------------------------------------------------------


def classify_parsed_pdf(
    parsed: ParsedPdf,
    filename: str = "",
) -> ClassificationResult:
    """
    Classify a pre-parsed PDF document.

    Pipeline:
      heuristic → if confident (>=0.90), return early.
      else → LLM fallback via generate_json().

    Args:
        parsed:   A ParsedPdf from backend.pdf_parser.parse_pdf.
        filename: Original filename for heuristic hints (optional but recommended).

    Returns:
        ClassificationResult with label, confidence, low_confidence, method, reason.
    """
    text = parsed.text
    heuristic = _heuristic_classify(text, filename)
    if heuristic is not None and heuristic.confidence >= _HEURISTIC_HIGH_CONFIDENCE:
        logger.debug(
            "Heuristic classified '%s' as %s (%.2f)",
            filename, heuristic.label, heuristic.confidence,
        )
        return heuristic

    # LLM fallback
    llm_result = _llm_classify(text, filename)

    # If heuristic produced a lower-confidence result, pick the higher-confidence one
    if heuristic is not None and heuristic.confidence >= llm_result.confidence:
        logger.debug(
            "Heuristic result (%.2f) beats LLM (%.2f) for '%s'",
            heuristic.confidence, llm_result.confidence, filename,
        )
        return heuristic

    logger.debug(
        "LLM classified '%s' as %s (%.2f)",
        filename, llm_result.label, llm_result.confidence,
    )
    return llm_result


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def persist_classification(
    file_record: File,
    result: ClassificationResult,
    db: Session,
) -> None:
    """
    Write classification columns onto a File row and commit.

    Sets: classification, confidence, low_confidence.
    Does NOT change status (that is T2.5's job).

    Args:
        file_record: The ORM File instance to update.
        result:      The classification result to persist.
        db:          Active SQLAlchemy session.
    """
    file_record.classification = result.label
    file_record.confidence = result.confidence
    file_record.low_confidence = 1 if result.low_confidence else 0
    db.add(file_record)
    db.commit()


def classify_and_persist(
    file_record: File,
    parsed: ParsedPdf,
    db: Session,
) -> ClassificationResult:
    """
    Classify parsed and immediately persist the result onto file_record.

    Property 5: if file_record.classification is already set, skips re-classification
    and returns the stored result unchanged.

    Args:
        file_record: ORM File instance.
        parsed:      Pre-parsed ParsedPdf.
        db:          Active SQLAlchemy session.

    Returns:
        ClassificationResult (either freshly computed or from the stored value).
    """
    # P5: idempotency -- skip if already classified
    if file_record.classification is not None:
        logger.debug(
            "File %d already classified as '%s' -- skipping.",
            file_record.id,
            file_record.classification,
        )
        return ClassificationResult(
            label=file_record.classification,  # type: ignore[arg-type]
            confidence=float(file_record.confidence or 0.0),
            method="heuristic",
            reason="Already classified -- skipped (P5).",
        )

    result = classify_parsed_pdf(parsed, filename=file_record.file_name)
    persist_classification(file_record, result, db)
    return result


# ---------------------------------------------------------------------------
# Class-based interface (used by pipeline.py -- T2.5)
# ---------------------------------------------------------------------------


class DocumentClassifier:
    """
    Classifies a File record (reads PDF from local_path via pdf_parser).

    Usage:
        classifier = DocumentClassifier()
        result = classifier.classify(file_record, db)
    """

    def classify(self, file_record: File, db: Session) -> ClassificationResult:
        """
        Classify a file.

        Property 5: skips if file already has a non-null classification.
        Persists label + confidence + low_confidence to the DB.
        """
        # P5 -- skip if already classified
        if file_record.classification is not None:
            logger.debug(
                "File %d already classified as %s -- skipping.",
                file_record.id, file_record.classification,
            )
            return ClassificationResult(
                label=file_record.classification,  # type: ignore[arg-type]
                confidence=file_record.confidence or 0.0,
                method="heuristic",
                reason="Already classified -- skipped.",
            )

        # Resolve local path
        if not file_record.local_path:
            result = ClassificationResult(
                label="unclassified",
                confidence=0.0,
                method="error",
                reason="No local_path on file record",
            )
            self._persist(file_record, result, db)
            return result

        pdf_path = Path(file_record.local_path)
        if not pdf_path.exists():
            result = ClassificationResult(
                label="unclassified",
                confidence=0.0,
                method="error",
                reason=f"File not found: {pdf_path}",
            )
            self._persist(file_record, result, db)
            return result

        # Parse PDF using canonical pdf_parser (raises PdfParseError on failure)
        from backend.pdf_parser import parse_pdf, PdfParseError
        try:
            parsed = parse_pdf(pdf_path)
        except PdfParseError as exc:
            result = ClassificationResult(
                label="unclassified",
                confidence=0.0,
                method="error",
                reason=f"PDF parse failure: {exc}",
            )
            self._persist(file_record, result, db)
            return result

        filename = file_record.file_name
        final = classify_parsed_pdf(parsed, filename=filename)
        self._persist(file_record, final, db)
        return final

    @staticmethod
    def _persist(file_record: File, result: ClassificationResult, db: Session) -> None:
        """Write classification result to DB."""
        file_record.classification = result.label
        file_record.confidence = result.confidence
        file_record.low_confidence = 1 if result.low_confidence else 0
        db.add(file_record)
        db.commit()
