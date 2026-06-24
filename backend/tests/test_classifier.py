"""
Tests for T2.2 Classifier — Properties 4, 5, 6.

Properties tested:
  P4: label ∈ valid set; confidence ∈ [0,1]; low_confidence ↔ confidence < 0.75
  P5: classify_and_persist skips re-classification when file already has a label
  P6: junk/unrelated files → 'other' or low_confidence

All Gemini network calls are monkeypatched via
``backend.llm.gemini_client._raw_generate`` — no real API calls in default run.

Heuristic path is tested with real corpus PDFs from data/files/.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.session import Base
from backend.db.models import File
from backend.pdf_parser import parse_pdf, ParsedPdf
from backend.classifier.document_classifier import (
    ClassificationResult,
    LOW_CONFIDENCE_THRESHOLD,
    classify_parsed_pdf,
    classify_and_persist,
    persist_classification,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "files"


def _make_db():
    """Create an in-memory SQLite DB with all tables for test isolation."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(conn, _rec):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session()


def _make_file(**kwargs) -> File:
    """Helper: create a File ORM object with minimal required fields."""
    defaults = dict(external_file_id=1, file_name="test.pdf", status="downloaded")
    defaults.update(kwargs)
    return File(**defaults)


def _parsed_pdf_from_text(text: str, filename: str = "test.pdf") -> ParsedPdf:
    """Build a minimal ParsedPdf from raw text (no actual PDF needed)."""
    return ParsedPdf(
        path=f"/fake/{filename}",
        n_pages=1,
        text=text,
        pages=(text,),
        tables=(),
    )


# ---------------------------------------------------------------------------
# P4: label / confidence / low_confidence invariants
# ---------------------------------------------------------------------------


class TestClassificationResultInvariants:
    """Property 4: dataclass enforces valid label + clamped confidence."""

    def test_valid_label_preserved(self):
        r = ClassificationResult(
            label="capital_account_statement",
            confidence=0.9,
            method="heuristic",
            reason="",
        )
        assert r.label == "capital_account_statement"

    def test_invalid_label_normalised_to_unclassified(self):
        r = ClassificationResult(
            label="garbage",  # type: ignore[arg-type]
            confidence=0.5,
            method="heuristic",
            reason="",
        )
        assert r.label == "unclassified"

    def test_confidence_clamped_above(self):
        r = ClassificationResult(label="report", confidence=1.5, method="heuristic", reason="")
        assert r.confidence == 1.0

    def test_confidence_clamped_below(self):
        r = ClassificationResult(label="report", confidence=-0.3, method="heuristic", reason="")
        assert r.confidence == 0.0

    def test_low_confidence_true_below_threshold(self):
        r = ClassificationResult(label="report", confidence=0.74, method="llm", reason="")
        assert r.low_confidence is True

    def test_low_confidence_false_at_threshold(self):
        r = ClassificationResult(label="report", confidence=0.75, method="llm", reason="")
        assert r.low_confidence is False

    def test_low_confidence_false_above_threshold(self):
        r = ClassificationResult(
            label="capital_account_statement",
            confidence=0.95,
            method="heuristic",
            reason="",
        )
        assert r.low_confidence is False

    def test_low_confidence_threshold_constant(self):
        """Threshold must be 0.75 (single source of truth)."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.75


# ---------------------------------------------------------------------------
# Heuristic path — real corpus PDFs
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not DATA_DIR.exists(),
    reason="data/files not present",
)
class TestHeuristicClassifier:
    """Heuristic path classifies obvious CAS and report files from real corpus."""

    def test_obvious_cas_by_filename(self):
        """File with 'CapitalAccount' in name → capital_account_statement via heuristic."""
        pdf_path = DATA_DIR / "22054_fund_alpha_Q2_2025_CapitalAccount__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("CAS file not present")
        parsed = parse_pdf(pdf_path)
        result = classify_parsed_pdf(parsed, filename=pdf_path.name)
        assert result.label == "capital_account_statement"
        assert result.method == "heuristic"
        assert result.confidence >= 0.90

    def test_obvious_cas_capacct(self):
        """File with 'capacct' in name → capital_account_statement via heuristic."""
        pdf_path = DATA_DIR / "22053_fund_beta_capacct_q3_2025__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("CAS file not present")
        parsed = parse_pdf(pdf_path)
        result = classify_parsed_pdf(parsed, filename=pdf_path.name)
        assert result.label == "capital_account_statement"
        assert result.method == "heuristic"

    def test_obvious_report_by_filename(self):
        """File with 'Update' or 'Commentary' in name → report via heuristic."""
        pdf_path = DATA_DIR / "22023_fund_alpha_Q1_2023_Update__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("Report file not present")
        parsed = parse_pdf(pdf_path)
        result = classify_parsed_pdf(parsed, filename=pdf_path.name)
        assert result.label == "report"
        assert result.method == "heuristic"
        assert result.confidence >= 0.90

    def test_report_commentary(self):
        """Beta FS Commentary → report."""
        pdf_path = DATA_DIR / "22028_fund_beta_FS_Commentary_Mar2022__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("Report file not present")
        parsed = parse_pdf(pdf_path)
        result = classify_parsed_pdf(parsed, filename=pdf_path.name)
        assert result.label == "report"


# ---------------------------------------------------------------------------
# LLM path — monkeypatched
# ---------------------------------------------------------------------------


class TestLLMClassifierMocked:
    """Mocked LLM path — no real API calls."""

    def test_llm_path_returns_correct_label(self, monkeypatch):
        """When heuristic is inconclusive, LLM result is used."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda prompt, system_prompt: '{"label": "report", "confidence": 0.87}',
        )
        parsed = _parsed_pdf_from_text(
            "This fund had strong performance this quarter.", filename="ambiguous.pdf"
        )
        result = classify_parsed_pdf(parsed, filename="ambiguous.pdf")
        assert result.label == "report"
        assert abs(result.confidence - 0.87) < 1e-6
        assert result.method == "llm"

    def test_llm_path_cas_label(self, monkeypatch):
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "capital_account_statement", "confidence": 0.91}',
        )
        parsed = _parsed_pdf_from_text("Some text", filename="ambiguous2.pdf")
        result = classify_parsed_pdf(parsed, filename="ambiguous2.pdf")
        assert result.label == "capital_account_statement"
        assert result.confidence == pytest.approx(0.91)

    def test_llm_low_confidence_flag(self, monkeypatch):
        """LLM returns confidence 0.60 → low_confidence True."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "report", "confidence": 0.60}',
        )
        parsed = _parsed_pdf_from_text("Unclear document.", filename="unclear.pdf")
        result = classify_parsed_pdf(parsed, filename="unclear.pdf")
        assert result.confidence == pytest.approx(0.60)
        assert result.low_confidence is True

    def test_llm_returns_invalid_label_normalised(self, monkeypatch):
        """LLM returns unknown label → normalised to unclassified."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "newsletter", "confidence": 0.80}',
        )
        parsed = _parsed_pdf_from_text("Newsletter text.", filename="news.pdf")
        result = classify_parsed_pdf(parsed, filename="news.pdf")
        assert result.label == "unclassified"

    def test_llm_json_parse_failure_returns_unclassified(self, monkeypatch):
        """If Gemini returns broken JSON on both attempts → unclassified/error."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: "NOT JSON AT ALL",
        )
        parsed = _parsed_pdf_from_text("Some text.", filename="bad.pdf")
        result = classify_parsed_pdf(parsed, filename="bad.pdf")
        assert result.label == "unclassified"
        assert result.method == "error"


# ---------------------------------------------------------------------------
# P6: Junk / other
# ---------------------------------------------------------------------------


class TestJunkClassification:
    """Property 6: junk/other PDFs → 'other' or low_confidence."""

    @pytest.mark.skipif(not DATA_DIR.exists(), reason="data/files not present")
    def test_junk_drawdown_notice(self, monkeypatch):
        """16976_345.pdf is a drawdown notice — should not be CAS or report."""
        import backend.llm.gemini_client as gc

        # LLM fallback: returns 'other' with low confidence
        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "other", "confidence": 0.55}',
        )
        pdf_path = DATA_DIR / "16976_345.pdf"
        if not pdf_path.exists():
            pytest.skip("Junk file not present")
        parsed = parse_pdf(pdf_path)
        result = classify_parsed_pdf(parsed, filename=pdf_path.name)
        # Must be other OR low_confidence (not a high-confidence CAS/report)
        assert result.label == "other" or result.low_confidence is True

    def test_minimal_junk_text_fallback_to_llm_other(self, monkeypatch):
        """Junk text with no recognized patterns → LLM → other + low_confidence."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "other", "confidence": 0.50}',
        )
        parsed = _parsed_pdf_from_text(
            "Meeting agenda for annual board review.", filename="345.pdf"
        )
        result = classify_parsed_pdf(parsed, filename="345.pdf")
        assert result.label == "other"
        assert result.low_confidence is True


# ---------------------------------------------------------------------------
# P5: idempotency — skip if already classified
# ---------------------------------------------------------------------------


class TestPersistClassification:
    """Property 5: persist skips re-classification when file already has a label."""

    def test_already_classified_skipped(self):
        db = _make_db()
        try:
            f = _make_file(external_file_id=100, classification="report", confidence=0.88)
            db.add(f)
            db.commit()
            db.refresh(f)

            # classify_and_persist should return the stored result without re-classifying
            parsed = _parsed_pdf_from_text("Some text", filename="existing.pdf")
            result = classify_and_persist(f, parsed, db)
            assert result.label == "report"
            assert result.confidence == pytest.approx(0.88)
        finally:
            db.close()

    def test_persist_writes_columns(self, monkeypatch):
        """persist_classification writes classification, confidence, low_confidence."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"label": "capital_account_statement", "confidence": 0.93}',
        )
        db = _make_db()
        try:
            f = _make_file(external_file_id=200)
            db.add(f)
            db.commit()
            db.refresh(f)

            parsed = _parsed_pdf_from_text("Some CAS text", filename="cas.pdf")
            # Manually build result and persist
            result = ClassificationResult(
                label="capital_account_statement",
                confidence=0.93,
                method="llm",
                reason="test",
            )
            persist_classification(f, result, db)
            db.refresh(f)

            assert f.classification == "capital_account_statement"
            assert f.confidence == pytest.approx(0.93)
            assert f.low_confidence == 0  # 0.93 >= 0.75
        finally:
            db.close()

    def test_persist_low_confidence_written_as_1(self):
        """When confidence < 0.75, low_confidence is stored as 1."""
        db = _make_db()
        try:
            f = _make_file(external_file_id=300)
            db.add(f)
            db.commit()
            db.refresh(f)

            result = ClassificationResult(
                label="other",
                confidence=0.50,
                method="llm",
                reason="uncertain",
            )
            persist_classification(f, result, db)
            db.refresh(f)

            assert f.low_confidence == 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Optional live test (skipped by default)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skip(reason="Live Gemini test — run with -m live to execute")
def test_live_classify_cas():
    """Hits real Gemini API — not run in default pytest invocation."""
    pdf_path = DATA_DIR / "22053_fund_beta_capacct_q3_2025__1_.pdf"
    if not pdf_path.exists():
        pytest.skip("CAS file not present")
    parsed = parse_pdf(pdf_path)
    result = classify_parsed_pdf(parsed, filename=pdf_path.name)
    assert result.label == "capital_account_statement"
    assert result.confidence >= 0.75
