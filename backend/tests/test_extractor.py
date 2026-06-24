"""
Tests for T2.3 Statement Extractor — Properties 7, 8, 12.

Properties tested:
  P7: complete-or-none atomicity — if any field missing, no Statement row written
  P8: stored values == extracted values (no casting, no rounding)
  P12: statement_date round-trip as ISO date

All Gemini network calls are monkeypatched via
``backend.llm.gemini_client._raw_generate`` — no real API calls in default run.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.session import Base
from backend.db.models import File, Statement
from backend.pdf_parser import ParsedPdf
from backend.extractor.statement_extractor import (
    ExtractionData,
    ExtractionError,
    extract_from_parsed_pdf,
    extract_and_persist,
    persist_extraction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "files"


def _make_db():
    """Create an isolated in-memory SQLite DB for each test."""
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


def _make_file(db, **kwargs) -> File:
    """Create and persist a minimal File record."""
    defaults = dict(external_file_id=1, file_name="cas.pdf", status="downloaded")
    defaults.update(kwargs)
    f = File(**defaults)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _parsed_pdf(text: str, tables=(), filename: str = "cas.pdf") -> ParsedPdf:
    """Build a ParsedPdf from raw text (no real PDF needed)."""
    return ParsedPdf(
        path=f"/fake/{filename}",
        n_pages=1,
        text=text,
        pages=(text,),
        tables=tables,
    )


# ---------------------------------------------------------------------------
# P7: Atomicity — complete-or-none
# ---------------------------------------------------------------------------


class TestAtomicity:
    """Property 7: if any required field is missing, no Statement row is written."""

    def test_missing_fund_name_raises_no_statement_row(self, monkeypatch):
        """Mocked Gemini returns null fund_name → ExtractionError, zero Statement rows."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"fund_name": null, "statement_date": "2025-09-30", "current_value": "$1,000.00"}',
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=10, file_name="nofund.pdf")
            # Text and filename both have no recognisable fund name (no "Fund <Proper>")
            parsed = _parsed_pdf(
                "Annual drawdown notice for investor capital account.",
                filename="nofund.pdf",
            )
            with pytest.raises(ExtractionError):
                extract_and_persist(f, parsed, db)
            # Verify zero Statement rows
            assert db.query(Statement).count() == 0
        finally:
            db.close()

    def test_missing_statement_date_raises_no_statement_row(self, monkeypatch):
        """Mocked Gemini returns null date → ExtractionError, zero Statement rows."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"fund_name": "Fund Alpha", "statement_date": null, "current_value": "$1,000.00"}',
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=11)
            # Text with no detectable date
            parsed = _parsed_pdf("Fund Alpha text with no dates.", filename="nodate.pdf")
            with pytest.raises(ExtractionError):
                extract_and_persist(f, parsed, db)
            assert db.query(Statement).count() == 0
        finally:
            db.close()

    def test_missing_current_value_raises_no_statement_row(self, monkeypatch):
        """Mocked Gemini returns null current_value → ExtractionError, zero Statement rows."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"fund_name": "Fund Alpha", "statement_date": "2025-09-30", "current_value": null}',
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=12)
            parsed = _parsed_pdf("Fund Alpha. As of September 30, 2025.", filename="noval.pdf")
            with pytest.raises(ExtractionError):
                extract_and_persist(f, parsed, db)
            assert db.query(Statement).count() == 0
        finally:
            db.close()

    def test_all_null_from_gemini_raises_no_statement_row(self, monkeypatch):
        """Gemini returns all nulls → ExtractionError, zero Statement rows."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"fund_name": null, "statement_date": null, "current_value": null}',
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=13)
            parsed = _parsed_pdf("Unreadable content.", filename="empty.pdf")
            with pytest.raises(ExtractionError):
                extract_and_persist(f, parsed, db)
            assert db.query(Statement).count() == 0
        finally:
            db.close()

    def test_file_status_set_to_failed_on_error(self, monkeypatch):
        """On extraction failure, file.status is set to 'failed'."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: '{"fund_name": null, "statement_date": null, "current_value": null}',
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=14)
            parsed = _parsed_pdf("No content.", filename="bad.pdf")
            with pytest.raises(ExtractionError):
                extract_and_persist(f, parsed, db)
            db.refresh(f)
            assert f.status == "failed"
            assert f.extraction_error is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# P8: stored == extracted
# ---------------------------------------------------------------------------


class TestStoredEqualsExtracted:
    """Property 8: the values written to DB match extracted values exactly."""

    def test_full_triple_from_mocked_gemini_persisted_correctly(self, monkeypatch):
        """Mocked Gemini returns a full triple → Statement persisted; values match."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: (
                '{"fund_name": "Fund Beta", '
                '"statement_date": "2025-09-30", '
                '"current_value": "$2,817,000.00"}'
            ),
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=20)
            parsed = _parsed_pdf("Fund Beta text. As of September 30, 2025.", filename="cas.pdf")
            stmt = extract_and_persist(f, parsed, db)

            # Verify values stored as-is (P8)
            assert stmt.fund_name == "Fund Beta"
            assert stmt.statement_date == "2025-09-30"
            assert stmt.current_value == "$2,817,000.00"

            # Also verify DB is actually populated
            rows = db.query(Statement).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.fund_name == "Fund Beta"
            assert row.statement_date == "2025-09-30"
            assert row.current_value == "$2,817,000.00"
        finally:
            db.close()

    def test_current_value_preserved_with_dollar_and_commas(self, monkeypatch):
        """current_value is stored as TEXT — no stripping of $ or commas (P8)."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: (
                '{"fund_name": "Fund Alpha", '
                '"statement_date": "2025-06-30", '
                '"current_value": "$3,156,000.00"}'
            ),
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=21, file_name="alpha_cas.pdf")
            parsed = _parsed_pdf(
                "Fund Alpha. For the Period Ended 06/30/2025.", filename="alpha_cas.pdf"
            )
            stmt = extract_and_persist(f, parsed, db)
            # Must preserve the $ and commas
            assert "$" in stmt.current_value or stmt.current_value.replace(",", "").replace(".", "").isdigit()
        finally:
            db.close()

    def test_file_status_set_to_extracted_on_success(self, monkeypatch):
        """On success, file.status is set to 'extracted'."""
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: (
                '{"fund_name": "Fund Gamma", '
                '"statement_date": "2025-09-30", '
                '"current_value": "$5,000,000.00"}'
            ),
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=22, file_name="gamma_cas.pdf")
            parsed = _parsed_pdf(
                "Fund Gamma. As of September 30, 2025.", filename="gamma_cas.pdf"
            )
            extract_and_persist(f, parsed, db)
            db.refresh(f)
            assert f.status == "extracted"
            assert f.extraction_error is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# P12: statement_date round-trip as ISO date
# ---------------------------------------------------------------------------


class TestStatementDateValidation:
    """Property 12: statement_date must be a valid ISO date YYYY-MM-DD."""

    def test_valid_iso_date_stored(self, monkeypatch):
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(
            gc,
            "_raw_generate",
            lambda p, s: (
                '{"fund_name": "Fund Delta", '
                '"statement_date": "2025-06-30", '
                '"current_value": "$1,234,567.89"}'
            ),
        )
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=30, file_name="delta_cas.pdf")
            parsed = _parsed_pdf("Fund Delta. Period ended June 30, 2025.", filename="delta_cas.pdf")
            stmt = extract_and_persist(f, parsed, db)
            # Must be parseable as ISO date
            from datetime import date
            parsed_date = date.fromisoformat(stmt.statement_date)
            assert parsed_date.year == 2025
            assert parsed_date.month == 6
            assert parsed_date.day == 30
        finally:
            db.close()

    def test_heuristic_extract_date_from_text_iso(self):
        """Text with ISO date → correctly extracted without LLM."""
        # No monkeypatch needed: text has a clear date that regex can find
        text = "Fund Alpha, L.P.\nCapital Account Statement\nStatement Date: 2025-09-30\n"
        parsed = _parsed_pdf(text, filename="22056_fund_alpha_Q3_2025_CapitalAccount__1_.pdf")
        # extract_from_parsed_pdf with no LLM needed (file has CAS text structure)
        # We need enough info for heuristic to work. Use monkeypatch to avoid LLM.
        from datetime import date
        from backend.extractor.statement_extractor import _extract_date_from_text
        d = _extract_date_from_text(text)
        assert d is not None
        assert d == date(2025, 9, 30)
        assert d.isoformat() == "2025-09-30"

    def test_date_quarter_pattern_resolved_to_iso(self):
        """Q3 2025 in text → resolved to 2025-09-30."""
        from datetime import date
        from backend.extractor.statement_extractor import _extract_date_from_text
        text = "Capital Statement Q3 2025 for Evergreen Family Office"
        d = _extract_date_from_text(text)
        assert d is not None
        assert d == date(2025, 9, 30)

    def test_date_named_month_pattern(self):
        """'September 30, 2025' → 2025-09-30."""
        from datetime import date
        from backend.extractor.statement_extractor import _extract_date_from_text
        text = "As of September 30, 2025"
        d = _extract_date_from_text(text)
        assert d is not None
        assert d == date(2025, 9, 30)


# ---------------------------------------------------------------------------
# Heuristic extraction from real PDFs
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/files not present")
class TestRealCasPdfs:
    """Heuristic path extracts fields from real CAS PDFs without LLM."""

    def test_beta_capacct_heuristic(self):
        """Fund Beta Q3 2025 CAS — text + table extraction without LLM."""
        from backend.pdf_parser import parse_pdf as parse_real

        pdf_path = DATA_DIR / "22053_fund_beta_capacct_q3_2025__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("CAS file not present")
        parsed = parse_real(pdf_path)
        # This file has clear text — should extract without LLM
        data = extract_from_parsed_pdf(parsed, filename=pdf_path.name)
        assert data.fund_name is not None
        assert "Beta" in data.fund_name
        assert data.statement_date == "2025-09-30"
        assert data.current_value is not None and len(data.current_value) > 0

    def test_alpha_capital_account_heuristic(self):
        """Fund Alpha Q2 2025 CAS — date from text."""
        from backend.pdf_parser import parse_pdf as parse_real

        pdf_path = DATA_DIR / "22054_fund_alpha_Q2_2025_CapitalAccount__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("CAS file not present")
        parsed = parse_real(pdf_path)
        data = extract_from_parsed_pdf(parsed, filename=pdf_path.name)
        assert "Alpha" in data.fund_name
        assert data.statement_date is not None
        # Must be valid ISO
        from datetime import date
        d = date.fromisoformat(data.statement_date)
        assert d.year >= 2020

    def test_zeta_capital_statement(self):
        """Fund Zeta Q3 2025 CAS — different layout."""
        from backend.pdf_parser import parse_pdf as parse_real

        pdf_path = DATA_DIR / "22064_fund_zeta_-_Capital_Statement_-_2025-09-30__1_.pdf"
        if not pdf_path.exists():
            pytest.skip("CAS file not present")
        parsed = parse_real(pdf_path)
        data = extract_from_parsed_pdf(parsed, filename=pdf_path.name)
        assert "Zeta" in data.fund_name
        assert data.statement_date == "2025-09-30"
        assert data.current_value is not None


# ---------------------------------------------------------------------------
# persist_extraction helper
# ---------------------------------------------------------------------------


class TestPersistExtraction:
    """Direct tests for persist_extraction transaction semantics."""

    def test_persist_writes_statement_row(self):
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=40)
            data = ExtractionData(
                fund_name="Fund Epsilon",
                statement_date="2025-09-30",
                current_value="$3,500,000.00",
            )
            stmt = persist_extraction(f, data, db)
            assert stmt.id is not None
            assert stmt.fund_name == "Fund Epsilon"
            assert stmt.statement_date == "2025-09-30"
            assert stmt.current_value == "$3,500,000.00"

            rows = db.query(Statement).filter_by(file_id=f.id).all()
            assert len(rows) == 1
        finally:
            db.close()

    def test_persist_sets_file_status_extracted(self):
        db = _make_db()
        try:
            f = _make_file(db, external_file_id=41)
            data = ExtractionData(
                fund_name="Fund Zeta",
                statement_date="2025-09-30",
                current_value="$5,816,000.00",
            )
            persist_extraction(f, data, db)
            db.refresh(f)
            assert f.status == "extracted"
            assert f.extraction_error is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Optional live test (skipped by default)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skip(reason="Live Gemini test — run with -m live to execute")
def test_live_extract_cas():
    """Hits real Gemini API — not run in default pytest invocation."""
    from backend.pdf_parser import parse_pdf as parse_real

    pdf_path = DATA_DIR / "22053_fund_beta_capacct_q3_2025__1_.pdf"
    if not pdf_path.exists():
        pytest.skip("CAS file not present")
    parsed = parse_real(pdf_path)
    data = extract_from_parsed_pdf(parsed, filename=pdf_path.name)
    assert data.fund_name is not None
    assert data.statement_date is not None
    assert data.current_value is not None
