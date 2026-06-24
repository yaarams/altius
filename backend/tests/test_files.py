"""
Tests for GET /api/files and GET /api/files/{id}/download.

Property 19: low_confidence flag is true when confidence < 0.75.

Uses an isolated in-memory SQLite DB with StaticPool — same pattern as
test_holdings.py.  No network, no Gemini.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routers.files import router
from backend.db.session import get_db


# ---------------------------------------------------------------------------
# In-memory DB helpers (mirrors test_holdings.py)
# ---------------------------------------------------------------------------

def _make_engine():
    """Create an isolated in-memory SQLite engine with StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE files (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                external_file_id INTEGER NOT NULL UNIQUE,
                deal_id          INTEGER,
                portal_doc_type  TEXT,
                file_name        TEXT NOT NULL DEFAULT 'test.pdf',
                file_url         TEXT,
                content_hash     TEXT,
                local_path       TEXT,
                download_ts      TEXT,
                status           TEXT NOT NULL DEFAULT 'extracted',
                classification   TEXT,
                confidence       REAL,
                low_confidence   INTEGER,
                extraction_error TEXT,
                indexed          INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE statements (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id        INTEGER NOT NULL REFERENCES files(id),
                fund_name      TEXT NOT NULL,
                statement_date TEXT NOT NULL,
                current_value  TEXT NOT NULL
            )
        """))
        conn.commit()
    return engine


def _insert_file(
    conn,
    ext_id: int,
    file_name: str = "test.pdf",
    classification: str | None = None,
    confidence: float | None = None,
    low_confidence: int | None = None,
    local_path: str | None = None,
    download_ts: str | None = None,
    created_at: str = "2025-01-15T10:00:00+00:00",
) -> int:
    conn.execute(
        text("""
            INSERT INTO files
                (external_file_id, file_name, status, classification, confidence,
                 low_confidence, local_path, download_ts, created_at)
            VALUES
                (:eid, :fn, 'extracted', :cls, :conf, :lc, :lp, :dts, :cat)
        """),
        {
            "eid": ext_id,
            "fn": file_name,
            "cls": classification,
            "conf": confidence,
            "lc": low_confidence,
            "lp": local_path,
            "dts": download_ts,
            "cat": created_at,
        },
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


def _insert_statement(
    conn, file_id: int, fund_name: str, statement_date: str, current_value: str = "1000000.00"
) -> int:
    conn.execute(
        text("""
            INSERT INTO statements (file_id, fund_name, statement_date, current_value)
            VALUES (:fid, :fn, :sd, :cv)
        """),
        {"fid": file_id, "fn": fund_name, "sd": statement_date, "cv": current_value},
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


def _make_test_client(seed_fn=None):
    """Build a TestClient backed by an isolated in-memory DB."""
    engine = _make_engine()
    if seed_fn is not None:
        with engine.connect() as conn:
            seed_fn(conn)
            conn.commit()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    test_app.dependency_overrides[get_db] = override_get_db

    return TestClient(test_app), engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListFilesShape:
    """test_list_files_shape: GET /api/files → 200, bare array, correct field types."""

    def test_empty_db_returns_empty_array(self):
        client, _ = _make_test_client()
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data == []

    def test_returns_bare_array_not_wrapped(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.9, low_confidence=0)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        # Must be a JSON array (list), NOT a dict like {"files": [...]}
        assert isinstance(data, list)

    def test_all_eight_fields_present(self):
        def seed(conn):
            fid = _insert_file(conn, 1, classification="capital_account_statement", confidence=0.95, low_confidence=0)
            _insert_statement(conn, fid, "Fund Alpha", "2025-03-31")

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]

        required_fields = {
            "file_id", "file_name", "doc_type", "classification_confidence",
            "low_confidence", "period", "fund_name", "uploaded_at",
        }
        assert required_fields <= set(item.keys()), f"Missing fields: {required_fields - set(item.keys())}"

    def test_file_id_is_string(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.9, low_confidence=0)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert isinstance(data[0]["file_id"], str), "file_id must be a string"

    def test_doc_type_is_one_of_three_literals(self):
        valid = {"capital_account_statement", "report", "other"}

        def seed(conn):
            _insert_file(conn, 1, classification="capital_account_statement", confidence=0.9)
            _insert_file(conn, 2, classification="report", confidence=0.9)
            _insert_file(conn, 3, classification=None)   # → "other"
            _insert_file(conn, 4, classification="unclassified")  # → "other"

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        for item in data:
            assert item["doc_type"] in valid, f"Unexpected doc_type: {item['doc_type']}"

    def test_results_ordered_by_file_id(self):
        def seed(conn):
            _insert_file(conn, 10, classification="report")
            _insert_file(conn, 20, classification="other")
            _insert_file(conn, 30, classification="capital_account_statement")

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        ids = [int(item["file_id"]) for item in data]
        assert ids == sorted(ids), "Results must be ordered by file_id"


class TestLowConfidenceFlag:
    """Property 19: low_confidence is true when confidence < 0.75."""

    def test_confidence_0_5_is_low(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.5, low_confidence=1)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["low_confidence"] is True

    def test_confidence_0_9_is_not_low(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.9, low_confidence=0)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["low_confidence"] is False

    def test_confidence_below_075_triggers_flag_even_without_db_flag(self):
        """Even if low_confidence column is NULL/0, confidence < 0.75 → flag true."""
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.74, low_confidence=0)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["low_confidence"] is True

    def test_confidence_exactly_075_is_not_low(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.75, low_confidence=0)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["low_confidence"] is False

    def test_db_flag_true_overrides_high_confidence(self):
        """If the DB column says low_confidence=1, we trust it."""
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.9, low_confidence=1)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["low_confidence"] is True

    def test_no_confidence_defaults_to_zero_not_low(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=None, low_confidence=None)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["classification_confidence"] == 0.0
        assert data[0]["low_confidence"] is False


class TestPeriodAndFundFromStatement:
    """test_period_and_fund_from_statement: latest statement fields exposed; null when none."""

    def test_file_with_statement_has_period_and_fund(self):
        def seed(conn):
            fid = _insert_file(conn, 1, classification="capital_account_statement", confidence=0.95)
            _insert_statement(conn, fid, "Fund Beta", "2025-06-30")

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["period"] == "2025-06-30"
        assert data[0]["fund_name"] == "Fund Beta"

    def test_file_without_statements_has_null_period_and_fund(self):
        def seed(conn):
            _insert_file(conn, 1, classification="report", confidence=0.9)

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["period"] is None
        assert data[0]["fund_name"] is None

    def test_latest_statement_date_chosen(self):
        """When multiple statements exist, period = max statement_date."""
        def seed(conn):
            fid = _insert_file(conn, 1, classification="capital_account_statement", confidence=0.95)
            _insert_statement(conn, fid, "Fund Early", "2024-03-31")
            _insert_statement(conn, fid, "Fund Latest", "2025-12-31")
            _insert_statement(conn, fid, "Fund Middle", "2025-06-30")

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["period"] == "2025-12-31"
        assert data[0]["fund_name"] == "Fund Latest"

    def test_uploaded_at_prefers_download_ts(self):
        def seed(conn):
            _insert_file(
                conn, 1,
                classification="report",
                confidence=0.9,
                download_ts="2025-05-01T12:00:00+00:00",
                created_at="2025-04-01T08:00:00+00:00",
            )

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["uploaded_at"] == "2025-05-01T12:00:00+00:00"

    def test_uploaded_at_falls_back_to_created_at(self):
        def seed(conn):
            _insert_file(
                conn, 1,
                classification="report",
                confidence=0.9,
                download_ts=None,
                created_at="2025-04-01T08:00:00+00:00",
            )

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        data = resp.json()
        assert data[0]["uploaded_at"] == "2025-04-01T08:00:00+00:00"


class TestDownload404Missing:
    """test_download_404_missing: 404 for unknown id and non-integer id."""

    def test_missing_file_id_returns_404(self):
        client, _ = _make_test_client()
        resp = client.get("/api/files/99999/download")
        assert resp.status_code == 404

    def test_non_integer_file_id_returns_404(self):
        client, _ = _make_test_client()
        resp = client.get("/api/files/abc/download")
        assert resp.status_code == 404

    def test_file_with_no_local_path_returns_404(self):
        def seed(conn):
            _insert_file(conn, 1, local_path=None)

        client, _ = _make_test_client(seed_fn=seed)
        # Get the inserted file's id
        resp = client.get("/api/files")
        fid = resp.json()[0]["file_id"]
        resp2 = client.get(f"/api/files/{fid}/download")
        assert resp2.status_code == 404

    def test_file_with_nonexistent_path_returns_404(self):
        def seed(conn):
            _insert_file(conn, 1, local_path="/nonexistent/path/does/not/exist.pdf")

        client, _ = _make_test_client(seed_fn=seed)
        resp = client.get("/api/files")
        fid = resp.json()[0]["file_id"]
        resp2 = client.get(f"/api/files/{fid}/download")
        assert resp2.status_code == 404


class TestDownloadServesPdf:
    """test_download_serves_pdf: 200 with application/pdf content-type."""

    def test_download_returns_200_with_pdf_content_type(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake pdf content")
            tmp_path = f.name

        try:
            def seed(conn):
                _insert_file(
                    conn, 1,
                    file_name="report.pdf",
                    classification="report",
                    confidence=0.9,
                    local_path=tmp_path,
                )

            client, _ = _make_test_client(seed_fn=seed)
            # Get the file id
            list_resp = client.get("/api/files")
            fid = list_resp.json()[0]["file_id"]

            resp = client.get(f"/api/files/{fid}/download")
            assert resp.status_code == 200
            assert "application/pdf" in resp.headers.get("content-type", "")
        finally:
            os.unlink(tmp_path)

    def test_download_content_matches_file(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            content = b"%PDF-1.4 some real content here"
            f.write(content)
            tmp_path = f.name

        try:
            def seed(conn):
                _insert_file(conn, 1, file_name="my_doc.pdf", local_path=tmp_path)

            client, _ = _make_test_client(seed_fn=seed)
            list_resp = client.get("/api/files")
            fid = list_resp.json()[0]["file_id"]

            resp = client.get(f"/api/files/{fid}/download")
            assert resp.status_code == 200
            assert resp.content == content
        finally:
            os.unlink(tmp_path)
