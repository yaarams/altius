"""
Tests for T3.1 Indexer — Property 17 (idempotent, bounded, no duplicates).

All Gemini network calls are monkeypatched:
    backend.llm.gemini_client.embed_text  → deterministic hash-based vector

Uses a temp ChromaDB dir and an in-memory SQLite seeded with real File rows
pointing at 2-3 real corpus PDFs.

Properties tested:
    P17a: index N docs → collection count = expected chunk count
    P17b: re-indexing the same file_id does not duplicate vectors (idempotent)
    P17c: junk/other-classified files are NOT indexed
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.session import Base
from backend.db.models import File, Statement

# ---------------------------------------------------------------------------
# Real corpus paths (skip tests gracefully if not present on disk)
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "files"

REPORT_PDF_1 = DATA_DIR / "22023_fund_alpha_Q1_2023_Update__1_.pdf"
REPORT_PDF_2 = DATA_DIR / "22024_fund_alpha_Q3_2021_Update__1_.pdf"
CAS_PDF_1 = DATA_DIR / "22054_fund_alpha_Q2_2025_CapitalAccount__1_.pdf"


def _pdfs_available() -> bool:
    return REPORT_PDF_1.exists() and REPORT_PDF_2.exists() and CAS_PDF_1.exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_embed(text: str) -> list[float]:
    """Deterministic 768-d embedding from text hash — no API call."""
    h = hashlib.sha256(text.encode()).digest()
    # Expand 32 bytes to 768 floats by repeating and normalising
    expanded = (h * 24)[:768]  # 24 * 32 = 768 bytes
    return [float(b) / 255.0 for b in expanded]


def _make_db():
    """In-memory SQLite with all tables."""
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


def _seed_file(db, external_file_id: int, file_name: str, local_path: str,
               classification: str = "report") -> File:
    f = File(
        external_file_id=external_file_id,
        file_name=file_name,
        local_path=local_path,
        classification=classification,
        status="downloaded",
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _seed_statement(db, file: File, fund_name: str = "Fund Alpha",
                    statement_date: str = "2025-06-30",
                    current_value: str = "1234567.89") -> Statement:
    s = Statement(
        file_id=file.id,
        fund_name=fund_name,
        statement_date=statement_date,
        current_value=current_value,
    )
    db.add(s)
    db.commit()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _pdfs_available(), reason="corpus PDFs not present")
def test_index_two_reports_idempotent(monkeypatch, tmp_path):
    """
    P17a: index 2 reports → collection has chunks for both.
    P17b: re-indexing same files → no new chunks (idempotent upsert).
    """
    import backend.llm.gemini_client as gc
    monkeypatch.setattr(gc, "embed_text", _fake_embed)

    chroma_path = str(tmp_path / "chroma")

    db = _make_db()
    _seed_file(db, 22023, REPORT_PDF_1.name, str(REPORT_PDF_1), "report")
    _seed_file(db, 22024, REPORT_PDF_2.name, str(REPORT_PDF_2), "report")

    from backend.indexer.indexer import index_documents, get_collection

    # First pass
    result1 = index_documents(db, chroma_path=chroma_path)
    assert result1["indexed"] == 2
    assert result1["failed"] == 0

    collection = get_collection(chroma_path)
    count_after_first = collection.count()
    assert count_after_first > 0, "Collection should have chunks after indexing"

    # Second pass (files.indexed==1 → skipped by default)
    result2 = index_documents(db, chroma_path=chroma_path)
    assert result2["indexed"] == 0
    assert result2["skipped"] == 2

    count_after_second = collection.count()
    assert count_after_second == count_after_first, (
        "P17b violated: re-indexing should not add duplicate chunks"
    )


@pytest.mark.skipif(not _pdfs_available(), reason="corpus PDFs not present")
def test_index_force_no_duplicates(monkeypatch, tmp_path):
    """
    P17b (force): force=True re-upserts same chunk ids → count unchanged.
    Upsert semantics: same id overwrites, never duplicates.
    """
    import backend.llm.gemini_client as gc
    monkeypatch.setattr(gc, "embed_text", _fake_embed)

    chroma_path = str(tmp_path / "chroma")

    db = _make_db()
    _seed_file(db, 22023, REPORT_PDF_1.name, str(REPORT_PDF_1), "report")

    from backend.indexer.indexer import index_documents, get_collection

    result1 = index_documents(db, chroma_path=chroma_path)
    count_first = get_collection(chroma_path).count()

    # Force re-index
    result2 = index_documents(db, chroma_path=chroma_path, force=True)
    assert result2["indexed"] == 1
    count_second = get_collection(chroma_path).count()

    assert count_second == count_first, (
        "P17b violated: forced re-index (upsert) must not duplicate chunks"
    )


@pytest.mark.skipif(not _pdfs_available(), reason="corpus PDFs not present")
def test_junk_not_indexed(monkeypatch, tmp_path):
    """
    P17c: files classified as 'other' are not indexed.
    """
    import backend.llm.gemini_client as gc
    monkeypatch.setattr(gc, "embed_text", _fake_embed)

    chroma_path = str(tmp_path / "chroma")

    db = _make_db()
    _seed_file(db, 16976, "345.pdf", str(DATA_DIR / "16976_345.pdf"), "other")

    from backend.indexer.indexer import index_documents, get_collection

    result = index_documents(db, chroma_path=chroma_path)
    assert result["indexed"] == 0

    count = get_collection(chroma_path).count()
    assert count == 0, "Junk/other files must not be indexed"


@pytest.mark.skipif(not _pdfs_available(), reason="corpus PDFs not present")
def test_cas_indexed_with_period(monkeypatch, tmp_path):
    """
    CAS files are indexed and period comes from Statement.statement_date.
    """
    import backend.llm.gemini_client as gc
    monkeypatch.setattr(gc, "embed_text", _fake_embed)

    chroma_path = str(tmp_path / "chroma")

    db = _make_db()
    cas_file = _seed_file(db, 22054, CAS_PDF_1.name, str(CAS_PDF_1), "capital_account_statement")
    _seed_statement(db, cas_file, statement_date="2025-06-30")

    from backend.indexer.indexer import index_documents, get_collection

    result = index_documents(db, chroma_path=chroma_path)
    assert result["indexed"] == 1

    collection = get_collection(chroma_path)
    assert collection.count() > 0

    # Check metadata of first chunk
    items = collection.get(include=["metadatas"])
    metadatas = items["metadatas"]
    assert any(m["period"] == "2025-06-30" for m in metadatas), (
        "CAS chunk metadata should carry the statement_date as period"
    )


def test_chunk_text_basic():
    """Unit test for _chunk_text — no PDF or Gemini involved."""
    from backend.indexer.indexer import _chunk_text

    # Short text → single chunk
    chunks = _chunk_text("hello world", chunk_size=800, overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == "hello world"

    # Long text → multiple chunks
    long_text = "A" * 2000
    chunks = _chunk_text(long_text, chunk_size=800, overlap=100)
    assert len(chunks) > 1

    # Ensure no chunk exceeds chunk_size
    for chunk in chunks:
        assert len(chunk) <= 800


def test_extract_period_from_filename():
    """Unit test for _extract_period heuristic — no DB needed."""
    from backend.indexer.indexer import _extract_period

    db = _make_db()

    # Q1_2023 pattern
    f = File(external_file_id=1, file_name="fund_alpha_Q1_2023_Update.pdf", status="downloaded")
    db.add(f)
    db.commit()
    period = _extract_period(f, db)
    assert period == "Q1 2023"

    # Mar2022 pattern
    f2 = File(external_file_id=2, file_name="fund_beta_FS_Commentary_Mar2022.pdf", status="downloaded")
    db.add(f2)
    db.commit()
    period2 = _extract_period(f2, db)
    assert period2 == "Mar 2022"

    # No pattern → None
    f3 = File(external_file_id=3, file_name="unknown.pdf", status="downloaded")
    db.add(f3)
    db.commit()
    period3 = _extract_period(f3, db)
    assert period3 is None


def test_extract_period_prefers_statement(monkeypatch):
    """Statement.statement_date takes priority over filename heuristic."""
    from backend.indexer.indexer import _extract_period

    db = _make_db()
    f = File(external_file_id=99, file_name="fund_alpha_Q1_2023_Update.pdf", status="downloaded")
    db.add(f)
    db.commit()

    s = Statement(file_id=f.id, fund_name="Alpha", statement_date="2023-03-31", current_value="999")
    db.add(s)
    db.commit()

    period = _extract_period(f, db)
    assert period == "2023-03-31"  # statement_date wins over filename


# ---------------------------------------------------------------------------
# Optional live test (skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.skipif(not _pdfs_available(), reason="corpus PDFs not present")
def test_live_embed_and_index(tmp_path):
    """
    Live test: real Gemini embed_text call.
    Skipped by default — run with: pytest -m live
    Requires GEMINI_API_KEY to be set.
    """
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

    chroma_path = str(tmp_path / "chroma")
    db = _make_db()
    _seed_file(db, 22023, REPORT_PDF_1.name, str(REPORT_PDF_1), "report")

    from backend.indexer.indexer import index_documents, get_collection

    result = index_documents(db, chroma_path=chroma_path)
    assert result["indexed"] == 1
    assert get_collection(chroma_path).count() > 0
