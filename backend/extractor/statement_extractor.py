"""
Statement extractor -- T2.3.

Extracts fund_name, statement_date (ISO), current_value (TEXT) from a
capital-account-statement PDF.

Strategy (ADR-006 pdfplumber primary):
  1. pdfplumber table scan (via ParsedPdf.tables_as_lists()) for current_value.
  2. Plain text regex scan for date, fund_name, current_value fallback.
  3. Gemini JSON fallback (generate_json) for any field still missing.

Atomicity (Properties 7, 8, 12):
  - If ANY field cannot be extracted/validated, raises ExtractionError.
  - No partial Statement row is written.
  - persist_extraction() uses a single DB transaction.

Validation:
  - statement_date must parse as ISO date (YYYY-MM-DD).
  - fund_name must be non-empty string.
  - current_value must be non-empty string (TEXT, not cast to float, P8).

Public API:
  extract_from_parsed_pdf(parsed, filename) -> ExtractionData  (raises ExtractionError)
  persist_extraction(file_record, data, db) -> Statement
  extract_and_persist(file_record, parsed, db) -> Statement
  ExtractionData, ExtractionError
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import File, Statement
from backend.pdf_parser import ParsedPdf

logger = logging.getLogger(__name__)


class ExtractionError(ValueError):
    """Raised when required fields cannot be extracted. No Statement row written (P7)."""


@dataclass
class ExtractionData:
    """Fully validated extraction result (all fields required).

    Attributes:
        fund_name:       Non-empty fund name string.
        statement_date:  ISO date string YYYY-MM-DD.
        current_value:   TEXT, original format, never cast to float (P8).
    """
    fund_name: str
    statement_date: str
    current_value: str


# ---------------------------------------------------------------------------
# Current-value label patterns (from design.md)
# ---------------------------------------------------------------------------

_CV_LABELS = [
    "ending capital balance",
    "closing nav",
    "ending nav",
    "partner’s capital — ending",
    "partner's capital - ending",
    "partners’ capital — ending",
    "partners' capital - ending",
    "net asset value",
    "ending balance",
    "closing balance",
    "partners’ capital end of period",
    "partners’ capital, end of period",
    "partners capital end of period",
    "total partners capital",
    "total partners’ capital",
    "ending partners capital",
    "ending partners’ capital",
    "partner’s capital, end of period",
    "partner’s capital — ending balance",
    # ASCII apostrophe variants
    "partner's capital — ending",
    "partners' capital — ending",
    "total partners' capital",
    "ending partners' capital",
    "partners' capital end of period",
    "partners' capital, end of period",
]

_CV_LABEL_ESCAPED = "|".join(re.escape(lbl) for lbl in _CV_LABELS)

_CV_LABEL_RE = re.compile(
    r"(" + _CV_LABEL_ESCAPED + r")"
    r"[\s:\-]*([$]?[\d,]+(?:\.[\d]+)?)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_QUARTER_END: dict[int, tuple[int, int]] = {
    1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31),
}

_MONTH_NAMES = (
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)

# "September 30, 2025" / "Sep 30 2025"
_DATE_NAMED_MONTH = re.compile(
    r"\b(" + _MONTH_NAMES + r")[\s\-]+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
# "30-Sep-2025" / "30 Sep 2025"
_DATE_DAY_NAMED = re.compile(
    r"\b(\d{1,2})[\s\-]+(" + _MONTH_NAMES + r")[\s\-]+(\d{4})\b",
    re.IGNORECASE,
)
# "2025-09-30"
_DATE_ISO = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
# "09/30/2025"
_DATE_US = re.compile(r"\b(\d{2})[-/](\d{2})[-/](\d{4})\b")
# "Q3 2025"
_DATE_QUARTER = re.compile(r"\bQ([1234])\s*(\d{4})\b", re.IGNORECASE)

_DATE_CONTEXT = re.compile(
    r"(?:as of|period end(?:ed|ing)?|quarter end(?:ed|ing)?|statement date"
    r"|through|ended|for the period)\s*",
    re.IGNORECASE,
)

_FUND_NAME_TEXT = re.compile(
    r"\bFund\s+(Alpha|Beta|Gamma|Delta|Epsilon|Zeta|[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b",
    re.IGNORECASE,
)
_FUND_NAME_FILE = re.compile(
    r"fund[_\s\-]*(alpha|beta|gamma|delta|epsilon|zeta)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_date(year: int, month: int, day: int) -> Optional[date]:
    """Return date object or None if values are invalid."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_date_from_text(text: str) -> Optional[date]:
    """Scan text for a statement/period-end date. Prefers context-tagged dates."""
    candidates: list[tuple[int, date]] = []

    def _score(start: int) -> int:
        prefix = text[max(0, start - 60): start]
        return 2 if _DATE_CONTEXT.search(prefix) else 1

    for m in _DATE_NAMED_MONTH.finditer(text):
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            d = _try_date(int(m.group(3)), mon, int(m.group(2)))
            if d:
                candidates.append((_score(m.start()), d))

    for m in _DATE_DAY_NAMED.finditer(text):
        mon = _MONTHS.get(m.group(2).lower())
        if mon:
            d = _try_date(int(m.group(3)), mon, int(m.group(1)))
            if d:
                candidates.append((_score(m.start()), d))

    for m in _DATE_ISO.finditer(text):
        d = _try_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            candidates.append((_score(m.start()), d))

    for m in _DATE_US.finditer(text):
        d = _try_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if d:
            candidates.append((_score(m.start()), d))

    for m in _DATE_QUARTER.finditer(text):
        q = int(m.group(1))
        yr = int(m.group(2))
        mon, day = _QUARTER_END[q]
        d = _try_date(yr, mon, day)
        if d:
            candidates.append((_score(m.start()), d))

    if not candidates:
        return None
    max_score = max(s for s, _ in candidates)
    top = [d for s, d in candidates if s == max_score]
    return max(top)


def _extract_current_value_from_tables(tables: list) -> Optional[str]:
    """Scan pdfplumber tables for a known current-value label."""
    label_re = re.compile(
        r"^\s*(" + _CV_LABEL_ESCAPED + r")\s*$",
        re.IGNORECASE,
    )
    combined_re = re.compile(
        r"(" + _CV_LABEL_ESCAPED + r")[\s:\-]*([$]?[\d,]+(?:\.[\d]+)?)",
        re.IGNORECASE,
    )
    for table in tables:
        # Multi-cell rows: label cell + value cell in same row
        for row in table:
            for i, cell in enumerate(row):
                if cell and label_re.match(cell):
                    for j, other in enumerate(row):
                        if j != i and other:
                            stripped = other.strip()
                            if re.match(r"[$]?[\d,]+(?:\.[\d]+)?$", stripped):
                                return stripped
        # Single-cell combined "Label $value"
        for row in table:
            for cell in row:
                if cell:
                    m = combined_re.search(cell)
                    if m:
                        return m.group(2).strip()
    return None


def _extract_current_value_from_text(text: str) -> Optional[str]:
    """Regex scan of text for current-value label + number."""
    for m in _CV_LABEL_RE.finditer(text):
        val = m.group(2).strip()
        if val:
            return val
    return None


def _extract_fund_name(text: str, filename: str) -> Optional[str]:
    """Extract fund name from text heading or filename fallback."""
    for m in _FUND_NAME_TEXT.finditer(text[:2000]):
        word = m.group(1).strip()
        return f"Fund {word.title()}"
    mf = _FUND_NAME_FILE.search(filename)
    if mf:
        return f"Fund {mf.group(1).title()}"
    return None


# ---------------------------------------------------------------------------
# Gemini fallback
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You are a financial data extractor. Given text from a capital account statement PDF, "
    "extract exactly three fields:\n"
    "  1. fund_name: name of the fund (e.g. Fund Alpha, Fund Beta).\n"
    "  2. statement_date: period-end date in ISO 8601 format YYYY-MM-DD.\n"
    "  3. current_value: investor ending capital/NAV as a string, "
    "preserving original formatting (e.g. $2,817,000.00). "
    "Known labels: ending capital balance, closing NAV, ending NAV, "
    "ending balance, total partners capital, partner capital ending.\n\n"
    'Return ONLY valid JSON: {"fund_name": str|null, "statement_date": str|null, '
    '"current_value": str|null}. Use null if not found. Never fabricate data.'
)


def _llm_extract(text: str) -> dict:
    """Call Gemini generate_json to extract the three fields."""
    from backend.llm.gemini_client import generate_json

    prompt = (
        f"Capital account statement text:\n\n{text[:6000]}\n\n"
        "Extract fund_name, statement_date (YYYY-MM-DD), current_value (original format). "
        "Return JSON with keys: fund_name, statement_date, current_value."
    )
    result = generate_json(prompt=prompt, system_prompt=_EXTRACT_SYSTEM)
    return {
        "fund_name": result.get("fund_name") or None,
        "statement_date": result.get("statement_date") or None,
        "current_value": result.get("current_value") or None,
    }


# ---------------------------------------------------------------------------
# Validation helpers (Property 12 -- round-trip)
# ---------------------------------------------------------------------------


def _validate_iso_date(s: str) -> str:
    """Validate and return canonical ISO date. Raises ExtractionError on failure."""
    try:
        parsed = date.fromisoformat(s.strip())
        return parsed.isoformat()
    except (ValueError, AttributeError) as exc:
        raise ExtractionError(
            f"statement_date {s!r} is not a valid ISO date (YYYY-MM-DD): {exc}"
        ) from exc


def _validate_nonempty(field_name: str, value: Optional[str]) -> str:
    """Return stripped value; raises ExtractionError if empty/None."""
    if not value or not value.strip():
        raise ExtractionError(f"Required field {field_name!r} is empty or missing")
    return value.strip()


# ---------------------------------------------------------------------------
# Pure extraction function (no DB)
# ---------------------------------------------------------------------------


def extract_from_parsed_pdf(parsed: ParsedPdf, filename: str = "") -> ExtractionData:
    """
    Extract fund_name, statement_date, current_value from a ParsedPdf.

    Strategy (ADR-006):
      1. pdfplumber tables (parsed.tables_as_lists()) for current_value.
      2. Text regex for date, fund_name, current_value fallback.
      3. Gemini JSON fallback for any field still missing.

    All three fields are required. If any cannot be extracted and validated,
    raises ExtractionError (no partial result -- Property 7 atomicity).

    Args:
        parsed:   ParsedPdf from backend.pdf_parser.parse_pdf.
        filename: Original filename for fund-name fallback hint.

    Returns:
        ExtractionData with fund_name, statement_date (ISO), current_value (TEXT).

    Raises:
        ExtractionError: if any required field is missing or fails validation.
    """
    text = parsed.text
    tables = parsed.tables_as_lists()

    fund_name: Optional[str] = _extract_fund_name(text, filename)
    statement_date_obj: Optional[date] = _extract_date_from_text(text)
    current_value: Optional[str] = _extract_current_value_from_tables(tables)
    if current_value is None:
        current_value = _extract_current_value_from_text(text)

    needs_llm = fund_name is None or statement_date_obj is None or current_value is None
    if needs_llm:
        logger.debug("Falling back to Gemini for missing fields in %r", filename)
        try:
            gem = _llm_extract(text)

            if fund_name is None:
                raw_fn = gem.get("fund_name")
                if raw_fn and isinstance(raw_fn, str) and raw_fn.strip():
                    fund_name = raw_fn.strip()

            if statement_date_obj is None:
                raw_date = gem.get("statement_date")
                if raw_date and isinstance(raw_date, str) and raw_date.strip():
                    try:
                        statement_date_obj = date.fromisoformat(raw_date.strip())
                    except ValueError:
                        logger.warning("Gemini returned unparseable date %r", raw_date)

            if current_value is None:
                raw_cv = gem.get("current_value")
                if raw_cv is not None:
                    cv_str = str(raw_cv).strip()
                    if cv_str:
                        current_value = cv_str

        except Exception as exc:
            logger.warning("Gemini extraction failed for %r: %s", filename, exc)

    # Atomicity check -- all three required
    missing: list[str] = []
    if not fund_name:
        missing.append("fund_name")
    if statement_date_obj is None:
        missing.append("statement_date")
    if not current_value:
        missing.append("current_value")

    if missing:
        raise ExtractionError(
            f"Could not extract required field(s): {', '.join(missing)} from {filename!r}"
        )

    # Round-trip validate (Property 12)
    iso_date = _validate_iso_date(statement_date_obj.isoformat())  # type: ignore[union-attr]
    fund_name_clean = _validate_nonempty("fund_name", fund_name)
    current_value_clean = _validate_nonempty("current_value", current_value)

    return ExtractionData(
        fund_name=fund_name_clean,
        statement_date=iso_date,
        current_value=current_value_clean,
    )


# ---------------------------------------------------------------------------
# Persist helper (atomic transaction -- Property 7)
# ---------------------------------------------------------------------------


def persist_extraction(file_record: File, data: ExtractionData, db: Session) -> Statement:
    """
    Write a Statement row inside a single transaction (Property 7 atomicity).

    On DB error: rollback + raise ExtractionError. No partial row left.

    Returns:
        The newly created Statement ORM instance.

    Raises:
        ExtractionError: if the DB write fails.
    """
    try:
        stmt = Statement(
            file_id=file_record.id,
            fund_name=data.fund_name,
            statement_date=data.statement_date,
            current_value=data.current_value,
        )
        db.add(stmt)
        file_record.status = "extracted"
        file_record.extraction_error = None
        db.add(file_record)
        db.commit()
        db.refresh(stmt)
        logger.info(
            "Persisted statement for file %d: fund=%r date=%s value=%s",
            file_record.id, data.fund_name, data.statement_date, data.current_value,
        )
        return stmt
    except Exception as exc:
        db.rollback()
        raise ExtractionError(
            f"Failed to persist Statement for file {file_record.id}: {exc}"
        ) from exc


def extract_and_persist(file_record: File, parsed: ParsedPdf, db: Session) -> Statement:
    """
    Extract + persist atomically.

    On extraction failure: sets file.status=failed + extraction_error, commits
    (for auditability), then re-raises ExtractionError.
    No Statement row is written on failure (Property 7).

    Returns:
        The newly created Statement ORM instance on success.

    Raises:
        ExtractionError: on any failure.
    """
    try:
        data = extract_from_parsed_pdf(parsed, filename=file_record.file_name)
    except ExtractionError as exc:
        file_record.extraction_error = str(exc)
        file_record.status = "failed"
        db.add(file_record)
        db.commit()
        raise
    return persist_extraction(file_record, data, db)
