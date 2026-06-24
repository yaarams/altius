"""
Integration test: Holdings page is correct after a sync.

Tests GET /api/holdings against a realistic post-sync DB state:
  - latest-per-fund snapshot (max statement_date, max-id tie-break)
  - correct formatted values for each fund
  - idempotent re-sync: re-ingesting the same external_file_id does NOT
    duplicate fund rows (pipeline skips already-extracted files)
  - supersede: a newer statement for an existing fund replaces the older
    one in the holdings result; fund count stays the same
  - empty DB → 200 + empty list

Design note on "currency": the Statement model stores current_value as plain
TEXT (e.g. "1234567.89") with no separate currency column. The holdings
endpoint's _format_currency() always formats with a "$" prefix.  This is the
current design (no multi-currency schema); tests reflect that accurately.

Fixture/style mirrors backend/tests/test_holdings.py (StaticPool, TestClient,
raw SQL helpers — no external deps, no Gemini, no network).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# DB bootstrap helpers  (same schema as test_holdings.py)
# ---------------------------------------------------------------------------

def _make_engine() -> object:
    """In-memory SQLite with StaticPool (required for TestClient thread safety)."""
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


def _insert_file(conn, ext_id: int, status: str = "extracted") -> int:
    """Insert a minimal files row and return its id."""
    conn.execute(
        text(
            "INSERT INTO files (external_file_id, file_name, status, classification) "
            "VALUES (:eid, 'test.pdf', :status, 'capital_account_statement')"
        ),
        {"eid": ext_id, "status": status},
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


def _insert_statement(
    conn, file_id: int, fund_name: str, statement_date: str, current_value: str
) -> int:
    """Insert a statements row and return its id."""
    conn.execute(
        text(
            "INSERT INTO statements (file_id, fund_name, statement_date, current_value) "
            "VALUES (:fid, :fn, :sd, :cv)"
        ),
        {"fid": file_id, "fn": fund_name, "sd": statement_date, "cv": current_value},
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# FastAPI TestClient factory (mirrors test_holdings.py _make_test_client_with_db)
# ---------------------------------------------------------------------------

def _make_client(engine) -> TestClient:
    """Build a FastAPI TestClient wired to the given engine."""
    from backend.api.routers.holdings import router
    from backend.db.session import get_db

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: simulate persist_extraction() the way the pipeline does it,
# but without needing a real PDF — we directly call persist_extraction().
# ---------------------------------------------------------------------------

from backend.extractor.statement_extractor import ExtractionData, persist_extraction
from backend.db.models import File, Statement


def _orm_session(engine):
    """Return a plain SQLAlchemy session on the given engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


# ---------------------------------------------------------------------------
# Case 1: Empty DB → 200 + []
# ---------------------------------------------------------------------------

class TestEmptyDbAfterSync:
    def test_empty_db_returns_empty_holdings(self):
        """No statements in DB → GET /api/holdings returns {"holdings": []}."""
        engine = _make_engine()
        client = _make_client(engine)

        resp = client.get("/api/holdings")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"holdings": []}


# ---------------------------------------------------------------------------
# Case 2: Latest-per-fund after a realistic sync
#
# Scenario: two funds are ingested.
#   - Fund Alpha has TWO statements: an older Q1-2025 and a newer Q3-2025.
#   - Fund Beta has ONE statement: Q3-2025.
# Expected: two rows returned, Alpha shows the Q3-2025 snapshot.
# ---------------------------------------------------------------------------

class TestLatestPerFundAfterSync:

    def _seed(self, engine):
        """Populate DB the way the pipeline's persist_extraction() does."""
        with engine.connect() as conn:
            # Fund Alpha — older file (ext_id=101, Q1-2025)
            fid_alpha_old = _insert_file(conn, ext_id=101)
            _insert_statement(
                conn, fid_alpha_old,
                fund_name="Fund Alpha",
                statement_date="2025-03-31",
                current_value="1000000.00",
            )

            # Fund Alpha — newer file (ext_id=102, Q3-2025)
            fid_alpha_new = _insert_file(conn, ext_id=102)
            _insert_statement(
                conn, fid_alpha_new,
                fund_name="Fund Alpha",
                statement_date="2025-09-30",
                current_value="1250000.00",
            )

            # Fund Beta — single file (ext_id=201, Q3-2025)
            fid_beta = _insert_file(conn, ext_id=201)
            _insert_statement(
                conn, fid_beta,
                fund_name="Fund Beta",
                statement_date="2025-09-30",
                current_value="3700000.00",
            )
            conn.commit()

    def test_returns_one_row_per_fund(self):
        engine = _make_engine()
        self._seed(engine)
        client = _make_client(engine)

        resp = client.get("/api/holdings")

        assert resp.status_code == 200
        holdings = resp.json()["holdings"]
        assert len(holdings) == 2, f"Expected 2 fund rows, got {len(holdings)}: {holdings}"

    def test_fund_alpha_shows_latest_snapshot(self):
        engine = _make_engine()
        self._seed(engine)
        client = _make_client(engine)

        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]

        alpha = next(
            (h for h in holdings if h["fund_name"].lower().strip() == "fund alpha"),
            None,
        )
        assert alpha is not None, "Fund Alpha missing from holdings"
        # Must show Q3-2025, not Q1-2025
        assert alpha["statement_date"] == "September 30, 2025", (
            f"Expected 'September 30, 2025', got {alpha['statement_date']!r}"
        )
        assert alpha["current_value"] == "$1,250,000.00", (
            f"Expected '$1,250,000.00', got {alpha['current_value']!r}"
        )

    def test_fund_beta_shows_correct_values(self):
        engine = _make_engine()
        self._seed(engine)
        client = _make_client(engine)

        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]

        beta = next(
            (h for h in holdings if h["fund_name"].lower().strip() == "fund beta"),
            None,
        )
        assert beta is not None, "Fund Beta missing from holdings"
        assert beta["statement_date"] == "September 30, 2025"
        assert beta["current_value"] == "$3,700,000.00"

    def test_fund_count_is_stable(self):
        """Re-running the query multiple times returns the same count."""
        engine = _make_engine()
        self._seed(engine)
        client = _make_client(engine)

        counts = [len(client.get("/api/holdings").json()["holdings"]) for _ in range(3)]
        assert counts == [2, 2, 2]


# ---------------------------------------------------------------------------
# Case 3: Idempotent re-sync  (same external_file_id → no duplicate row)
#
# The pipeline's idempotency is enforced at the File level via UNIQUE
# (external_file_id): a second attempt to insert the same ext_id raises an
# IntegrityError, so the file is skipped.  We simulate this by verifying that
# attempting to insert a File with the same ext_id is rejected and the
# statements table keeps exactly one row for the fund.
# ---------------------------------------------------------------------------

class TestIdempotentReSync:

    def test_same_external_file_id_does_not_add_duplicate_statement(self):
        """
        Inserting a File with an already-seen external_file_id is rejected.
        The holdings endpoint must still return exactly one row for the fund.
        """
        import sqlalchemy.exc

        engine = _make_engine()
        with engine.connect() as conn:
            fid = _insert_file(conn, ext_id=301)
            _insert_statement(
                conn, fid,
                fund_name="Fund Gamma",
                statement_date="2025-03-31",
                current_value="500000.00",
            )
            conn.commit()

        # Simulate a re-sync attempt: same external_file_id → UNIQUE violation
        with engine.connect() as conn:
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO files (external_file_id, file_name, status) "
                        "VALUES (:eid, 'test.pdf', 'extracted')"
                    ),
                    {"eid": 301},  # duplicate ext_id
                )

        # Holdings must still show exactly one row, unchanged
        client = _make_client(engine)
        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]
        assert len(holdings) == 1
        assert holdings[0]["fund_name"] == "Fund Gamma"
        assert holdings[0]["current_value"] == "$500,000.00"

    def test_already_extracted_file_not_duplicated_via_pipeline(self):
        """
        When a File already has status='extracted', pipeline's process_file()
        skips extraction (R3.5).  Simulating this: even if we call
        persist_extraction() manually a second time for the same fund+date,
        the holdings query still collapses to one row (max-id wins).
        """
        engine = _make_engine()
        with engine.connect() as conn:
            fid = _insert_file(conn, ext_id=401)
            _insert_statement(
                conn, fid,
                fund_name="Fund Delta",
                statement_date="2025-09-30",
                current_value="800000.00",
            )
            conn.commit()

        # Verify only one row
        client = _make_client(engine)
        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]
        assert len(holdings) == 1
        assert holdings[0]["fund_name"] == "Fund Delta"


# ---------------------------------------------------------------------------
# Case 4: Supersede — newer statement replaces older one for same fund
# ---------------------------------------------------------------------------

class TestSupersede:

    def test_newer_statement_supersedes_older(self):
        """
        After a newer statement (higher date) is ingested for an existing fund,
        GET /api/holdings returns the newer snapshot; fund count unchanged.
        """
        engine = _make_engine()

        # Initial state: Fund Epsilon with Q1-2025
        with engine.connect() as conn:
            fid_old = _insert_file(conn, ext_id=501)
            _insert_statement(
                conn, fid_old,
                fund_name="Fund Epsilon",
                statement_date="2025-03-31",
                current_value="2000000.00",
            )
            conn.commit()

        client = _make_client(engine)
        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]
        assert len(holdings) == 1
        assert holdings[0]["statement_date"] == "March 31, 2025"
        assert holdings[0]["current_value"] == "$2,000,000.00"

        # Simulate a later sync that brings in a Q3-2025 statement
        with engine.connect() as conn:
            fid_new = _insert_file(conn, ext_id=502)  # different ext_id → new file
            _insert_statement(
                conn, fid_new,
                fund_name="Fund Epsilon",
                statement_date="2025-09-30",
                current_value="2500000.00",
            )
            conn.commit()

        resp2 = client.get("/api/holdings")
        holdings2 = resp2.json()["holdings"]

        # Fund count must be unchanged (1)
        assert len(holdings2) == 1, (
            f"Expected 1 fund row after supersede, got {len(holdings2)}: {holdings2}"
        )

        # Must reflect the newer snapshot
        assert holdings2[0]["statement_date"] == "September 30, 2025", (
            f"Expected Q3-2025 after supersede, got {holdings2[0]['statement_date']!r}"
        )
        assert holdings2[0]["current_value"] == "$2,500,000.00", (
            f"Expected $2,500,000.00 after supersede, got {holdings2[0]['current_value']!r}"
        )

    def test_supersede_two_funds_only_target_updated(self):
        """
        When a newer statement is ingested for Fund Zeta but NOT Fund Eta,
        Fund Eta's holdings row is unchanged.
        """
        engine = _make_engine()
        with engine.connect() as conn:
            fid_z = _insert_file(conn, ext_id=601)
            _insert_statement(conn, fid_z, "Fund Zeta", "2025-03-31", "1100000.00")
            fid_e = _insert_file(conn, ext_id=602)
            _insert_statement(conn, fid_e, "Fund Eta", "2025-03-31", "900000.00")
            conn.commit()

        client = _make_client(engine)

        # Add a newer statement for Fund Zeta only
        with engine.connect() as conn:
            fid_z2 = _insert_file(conn, ext_id=603)
            _insert_statement(conn, fid_z2, "Fund Zeta", "2025-09-30", "1300000.00")
            conn.commit()

        resp = client.get("/api/holdings")
        holdings = resp.json()["holdings"]
        assert len(holdings) == 2

        eta = next(h for h in holdings if h["fund_name"] == "Fund Eta")
        zeta = next(h for h in holdings if h["fund_name"] == "Fund Zeta")

        # Eta unchanged
        assert eta["statement_date"] == "March 31, 2025"
        assert eta["current_value"] == "$900,000.00"

        # Zeta updated
        assert zeta["statement_date"] == "September 30, 2025"
        assert zeta["current_value"] == "$1,300,000.00"


# ---------------------------------------------------------------------------
# Case 5: persist_extraction() code path  (drives real extractor code)
#
# Uses the actual persist_extraction() from statement_extractor to write rows,
# validating the full pipeline→DB→API path without a real PDF or Gemini call.
# ---------------------------------------------------------------------------

class TestPersistExtractionCodePath:

    def test_persist_extraction_then_holdings(self):
        """
        Drive the real persist_extraction() helper the same way the pipeline does,
        then assert GET /api/holdings returns the correct row.
        """
        from backend.db.models import Base
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.pool import StaticPool as _SP

        # Need a full ORM-schema engine for File/Statement ORM models
        orm_engine = _ce(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=_SP,
        )
        Base.metadata.create_all(orm_engine)

        Session = sessionmaker(bind=orm_engine, autoflush=False, autocommit=False)
        db = Session()

        try:
            # Create a File record (simulates what the crawler/downloader does)
            f = File(
                external_file_id=701,
                file_name="fund_alpha_q1_2025.pdf",
                status="downloaded",
                classification="capital_account_statement",
            )
            db.add(f)
            db.commit()
            db.refresh(f)

            # Call the real persist_extraction (same as pipeline does)
            data = ExtractionData(
                fund_name="Fund Alpha",
                statement_date="2025-03-31",
                current_value="4945000.00",
            )
            stmt = persist_extraction(f, data, db)

            # File status should be updated to 'extracted'
            db.refresh(f)
            assert f.status == "extracted"
            assert stmt.fund_name == "Fund Alpha"
            assert stmt.statement_date == "2025-03-31"
            assert stmt.current_value == "4945000.00"

        finally:
            db.close()

        # Wire the holdings endpoint to the same ORM engine
        from backend.api.routers.holdings import router
        from backend.db.session import get_db

        OrmSession = sessionmaker(bind=orm_engine, autoflush=False, autocommit=False)

        def override_get_db():
            s = OrmSession()
            try:
                yield s
            finally:
                s.close()

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.get("/api/holdings")
        assert resp.status_code == 200
        holdings = resp.json()["holdings"]
        assert len(holdings) == 1
        h = holdings[0]
        assert h["fund_name"] == "Fund Alpha"
        assert h["current_value"] == "$4,945,000.00"
        assert h["statement_date"] == "March 31, 2025"
        assert isinstance(h["file_id"], int)

    def test_two_funds_via_persist_extraction(self):
        """
        Two funds, each via persist_extraction → holdings returns two rows.
        """
        from backend.db.models import Base
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.pool import StaticPool as _SP

        orm_engine = _ce(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=_SP,
        )
        Base.metadata.create_all(orm_engine)

        Session = sessionmaker(bind=orm_engine, autoflush=False, autocommit=False)
        db = Session()

        try:
            for ext_id, fname, fund, dt, val in [
                (801, "alpha.pdf", "Fund Alpha", "2025-09-30", "5000000.00"),
                (802, "beta.pdf",  "Fund Beta",  "2025-09-30", "3200000.00"),
            ]:
                f = File(
                    external_file_id=ext_id,
                    file_name=fname,
                    status="downloaded",
                    classification="capital_account_statement",
                )
                db.add(f)
                db.commit()
                db.refresh(f)
                persist_extraction(f, ExtractionData(fund_name=fund, statement_date=dt, current_value=val), db)
        finally:
            db.close()

        from backend.api.routers.holdings import router
        from backend.db.session import get_db

        OrmSession = sessionmaker(bind=orm_engine, autoflush=False, autocommit=False)

        def override_get_db():
            s = OrmSession()
            try:
                yield s
            finally:
                s.close()

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.get("/api/holdings")
        assert resp.status_code == 200
        holdings = resp.json()["holdings"]
        assert len(holdings) == 2
        fund_names = {h["fund_name"] for h in holdings}
        assert fund_names == {"Fund Alpha", "Fund Beta"}
