"""
Tests for GET /api/holdings — Property 9, currency/date formatting, empty state.

# Feature: investor-document-platform, Property 9: Holdings query returns one row
# per fund with the latest date (MAX(id) tie-break when dates are equal).

Uses an isolated in-memory SQLite DB — does NOT depend on data/app.db.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=5000,
)
settings.load_profile("ci")

# ---------------------------------------------------------------------------
# In-memory DB helpers
# ---------------------------------------------------------------------------

def _make_engine(use_static_pool: bool = False):
    """Create an isolated in-memory SQLite engine with the required schema.

    use_static_pool=True forces all connections to share a single underlying
    sqlite3 connection, which is necessary when FastAPI's TestClient runs
    endpoint handlers in a worker thread (otherwise each thread gets a fresh
    empty :memory: database).
    """
    from sqlalchemy.pool import StaticPool

    kwargs: dict = {}
    if use_static_pool:
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    else:
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine("sqlite:///:memory:", **kwargs)
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


def _insert_file(conn, ext_id: int) -> int:
    """Insert a minimal files row and return its id."""
    conn.execute(
        text("INSERT INTO files (external_file_id, file_name, status) VALUES (:eid, 'test.pdf', 'extracted')"),
        {"eid": ext_id},
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


def _insert_statement(conn, file_id: int, fund_name: str, statement_date: str, current_value: str) -> int:
    conn.execute(
        text("INSERT INTO statements (file_id, fund_name, statement_date, current_value) VALUES (:fid, :fn, :sd, :cv)"),
        {"fid": file_id, "fn": fund_name, "sd": statement_date, "cv": current_value},
    )
    row = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# The holdings SQL (mirrors holdings.py)
# ---------------------------------------------------------------------------

_HOLDINGS_SQL = """
SELECT s.fund_name, s.current_value, s.statement_date, s.file_id
FROM statements s
INNER JOIN (
    SELECT
        lower(trim(fund_name))  AS norm_fund,
        MAX(statement_date)     AS max_date
    FROM statements
    GROUP BY lower(trim(fund_name))
) by_date
    ON lower(trim(s.fund_name)) = by_date.norm_fund
    AND s.statement_date = by_date.max_date
INNER JOIN (
    SELECT
        lower(trim(fund_name))  AS norm_fund,
        MAX(statement_date)     AS max_date,
        MAX(id)                 AS max_id
    FROM statements
    WHERE (lower(trim(fund_name)), statement_date) IN (
        SELECT lower(trim(fund_name)), MAX(statement_date)
        FROM statements
        GROUP BY lower(trim(fund_name))
    )
    GROUP BY lower(trim(fund_name))
) tie_break
    ON lower(trim(s.fund_name)) = tie_break.norm_fund
    AND s.statement_date = tie_break.max_date
    AND s.id = tie_break.max_id
ORDER BY lower(trim(s.fund_name))
"""


def _run_holdings_query(conn) -> list[dict]:
    rows = conn.execute(text(_HOLDINGS_SQL)).fetchall()
    return [
        {"fund_name": r[0], "current_value": r[1], "statement_date": r[2], "file_id": r[3]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Helper: format helpers (mirror from holdings.py)
# ---------------------------------------------------------------------------

def _format_currency(value_str: str) -> str:
    try:
        d = Decimal(value_str)
        return f"${d:,.2f}"
    except Exception:
        return value_str


def _format_date(date_str: str) -> str:
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return date_str


# ---------------------------------------------------------------------------
# Example-based tests
# ---------------------------------------------------------------------------

class TestEmptyState:
    def test_no_statements_returns_empty(self):
        engine = _make_engine()
        with engine.connect() as conn:
            rows = _run_holdings_query(conn)
        assert rows == []


class TestCurrencyAndDateFormatting:
    def test_currency_formatting(self):
        assert _format_currency("1234567.89") == "$1,234,567.89"
        assert _format_currency("0.00") == "$0.00"
        assert _format_currency("1000000") == "$1,000,000.00"
        assert _format_currency("15464166") == "$15,464,166.00"

    def test_date_formatting(self):
        assert _format_date("2025-03-31") == "March 31, 2025"
        assert _format_date("2025-09-30") == "September 30, 2025"
        assert _format_date("2021-03-31") == "March 31, 2021"

    def test_single_statement_formatted_correctly(self):
        engine = _make_engine()
        with engine.connect() as conn:
            fid = _insert_file(conn, 1)
            _insert_statement(conn, fid, "Fund Alpha, L.P.", "2025-09-30", "4945000.00")
            conn.commit()
            rows = _run_holdings_query(conn)

        assert len(rows) == 1
        assert _format_currency(rows[0]["current_value"]) == "$4,945,000.00"
        assert _format_date(rows[0]["statement_date"]) == "September 30, 2025"


class TestOneRowPerFund:
    def test_two_statements_same_fund_returns_latest(self):
        engine = _make_engine()
        with engine.connect() as conn:
            fid1 = _insert_file(conn, 1)
            fid2 = _insert_file(conn, 2)
            _insert_statement(conn, fid1, "Fund Alpha, L.P.", "2025-03-31", "1000000.00")
            _insert_statement(conn, fid2, "Fund Alpha, L.P.", "2025-09-30", "2000000.00")
            conn.commit()
            rows = _run_holdings_query(conn)

        assert len(rows) == 1
        assert rows[0]["statement_date"] == "2025-09-30"
        assert rows[0]["current_value"] == "2000000.00"

    def test_case_insensitive_fund_grouping(self):
        """'Fund Alpha' and 'FUND ALPHA' should collapse to one row."""
        engine = _make_engine()
        with engine.connect() as conn:
            fid1 = _insert_file(conn, 1)
            fid2 = _insert_file(conn, 2)
            _insert_statement(conn, fid1, "Fund Alpha", "2025-03-31", "1000000.00")
            _insert_statement(conn, fid2, "FUND ALPHA", "2025-09-30", "2000000.00")
            conn.commit()
            rows = _run_holdings_query(conn)

        assert len(rows) == 1
        assert rows[0]["statement_date"] == "2025-09-30"

    def test_whitespace_normalization(self):
        """'  Fund Alpha  ' and 'Fund Alpha' should be treated as same fund."""
        engine = _make_engine()
        with engine.connect() as conn:
            fid1 = _insert_file(conn, 1)
            fid2 = _insert_file(conn, 2)
            _insert_statement(conn, fid1, "  Fund Alpha  ", "2025-03-31", "1000000.00")
            _insert_statement(conn, fid2, "Fund Alpha", "2025-09-30", "2000000.00")
            conn.commit()
            rows = _run_holdings_query(conn)

        assert len(rows) == 1
        assert rows[0]["statement_date"] == "2025-09-30"

    def test_max_id_tiebreaker_equal_dates(self):
        """When two rows have same fund + same date, highest id wins."""
        engine = _make_engine()
        with engine.connect() as conn:
            fid1 = _insert_file(conn, 1)
            fid2 = _insert_file(conn, 2)
            sid1 = _insert_statement(conn, fid1, "Fund Alpha", "2025-09-30", "1111111.00")
            sid2 = _insert_statement(conn, fid2, "Fund Alpha", "2025-09-30", "2222222.00")
            conn.commit()
            rows = _run_holdings_query(conn)

        # sid2 > sid1, so the row with value 2222222.00 wins
        assert len(rows) == 1
        assert rows[0]["current_value"] == "2222222.00"

    def test_multiple_funds_one_row_each(self):
        engine = _make_engine()
        with engine.connect() as conn:
            for i, (fund, val) in enumerate([
                ("Fund Alpha", "1000000"),
                ("Fund Beta", "2000000"),
                ("Fund Gamma", "3000000"),
            ], start=1):
                fid = _insert_file(conn, i)
                _insert_statement(conn, fid, fund, "2025-09-30", val)
            conn.commit()
            rows = _run_holdings_query(conn)

        assert len(rows) == 3
        norm_funds = {r["fund_name"].lower().strip() for r in rows}
        assert norm_funds == {"fund alpha", "fund beta", "fund gamma"}


# ---------------------------------------------------------------------------
# Property 9: Hypothesis-based tests
# ---------------------------------------------------------------------------

# Strategies
fund_name_base = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters=" ,.",
        # Restrict to ASCII range to avoid Python/SQLite lower() mismatch
        # (e.g. ß.upper() == "SS" in Python but lower("SS") != "ß" in SQLite)
        max_codepoint=127,
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())  # must have non-whitespace

iso_date = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2026, 12, 31),
).map(lambda d: d.isoformat())

positive_value = st.decimals(
    min_value=Decimal("1000"),
    max_value=Decimal("99999999"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
).map(str)


@given(
    base_names=st.lists(fund_name_base, min_size=1, max_size=5, unique_by=lambda s: s.lower().strip()),
    dates_per_fund=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=10000)
def test_property9_one_row_per_normalized_fund(base_names, dates_per_fund):
    """
    Property 9: For any collection of statements (including duplicates, variants),
    the holdings query returns exactly one row per normalized fund name with the
    max statement_date (highest id tie-breaks equal dates).
    """
    engine = _make_engine()

    # Track expected winner per normalized fund
    expected: dict[str, dict] = {}  # norm_fund -> {date, id, value}

    ext_id_counter = [0]

    def next_ext_id():
        ext_id_counter[0] += 1
        return ext_id_counter[0]

    with engine.connect() as conn:
        stmt_id_counter = [0]

        for base_name in base_names:
            norm = base_name.lower().strip()
            # Generate a few date variants
            dates = sorted({
                f"202{i}-0{j+1}-01"
                for i in range(3, 7)
                for j in range(min(dates_per_fund, 12))
                if j < dates_per_fund
            })[:dates_per_fund]

            for dt in dates:
                # Possibly insert 1 or 2 rows for the same (fund, date)
                for variant_idx in range(2):
                    fid = _insert_file(conn, next_ext_id())
                    # Vary case/whitespace for some
                    variant_name = base_name.upper() if variant_idx == 1 else base_name
                    val = f"{1000000 + stmt_id_counter[0] * 1000}.00"
                    sid = _insert_statement(conn, fid, variant_name, dt, val)
                    stmt_id_counter[0] += 1

                    # Track if this row should be the winner
                    if norm not in expected:
                        expected[norm] = {"date": dt, "id": sid, "value": val}
                    else:
                        prev = expected[norm]
                        if dt > prev["date"] or (dt == prev["date"] and sid > prev["id"]):
                            expected[norm] = {"date": dt, "id": sid, "value": val}

        conn.commit()
        rows = _run_holdings_query(conn)

    # One row per normalized fund
    assert len(rows) == len(expected), (
        f"Expected {len(expected)} rows, got {len(rows)}: {rows}"
    )

    # Each row has the correct max date
    result_by_norm = {r["fund_name"].lower().strip(): r for r in rows}
    for norm_fund, exp in expected.items():
        assert norm_fund in result_by_norm, f"Fund {norm_fund!r} missing from results"
        got = result_by_norm[norm_fund]
        assert got["statement_date"] == exp["date"], (
            f"Fund {norm_fund!r}: expected date {exp['date']}, got {got['statement_date']}"
        )


@given(
    same_date_count=st.integers(min_value=2, max_value=6),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=10000)
def test_property9_max_id_tiebreak(same_date_count):
    """
    Property 9 (tie-break): when N statements share the same fund+date, the one
    with the highest id is returned.
    """
    engine = _make_engine()
    with engine.connect() as conn:
        inserted_ids = []
        for i in range(same_date_count):
            fid = _insert_file(conn, i + 1)
            sid = _insert_statement(conn, fid, "Fund Test", "2025-09-30", f"{(i + 1) * 100000}.00")
            inserted_ids.append((sid, f"{(i + 1) * 100000}.00"))
        conn.commit()
        rows = _run_holdings_query(conn)

    assert len(rows) == 1
    winning_id, winning_val = max(inserted_ids, key=lambda x: x[0])
    assert rows[0]["current_value"] == winning_val


# ---------------------------------------------------------------------------
# FastAPI integration: empty state and live endpoint via TestClient
# ---------------------------------------------------------------------------

def _make_test_client_with_db(seed_fn=None):
    """
    Build a FastAPI TestClient backed by an isolated in-memory SQLite DB.
    Uses StaticPool so the worker thread sees the same DB as the setup code.
    seed_fn(conn) is called to insert test data before the client is created.
    Returns (client, engine).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from backend.api.routers.holdings import router
    from backend.db.session import get_db

    engine = _make_engine(use_static_pool=True)
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


def test_api_empty_state():
    """GET /api/holdings with empty DB returns {"holdings": []}."""
    client, _ = _make_test_client_with_db()
    resp = client.get("/api/holdings")
    assert resp.status_code == 200
    assert resp.json() == {"holdings": []}


def test_api_returns_formatted_rows():
    """GET /api/holdings returns currency + date formatted rows from the injected DB."""
    def seed(conn):
        fid = _insert_file(conn, 1)
        _insert_statement(conn, fid, "Fund Test", "2025-03-31", "1234567.89")

    client, _ = _make_test_client_with_db(seed_fn=seed)
    resp = client.get("/api/holdings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["holdings"]) == 1
    row = data["holdings"][0]
    assert row["fund_name"] == "Fund Test"
    assert row["current_value"] == "$1,234,567.89"
    assert row["statement_date"] == "March 31, 2025"
    assert isinstance(row["file_id"], int)
