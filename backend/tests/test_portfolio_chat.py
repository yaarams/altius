"""
Portfolio-aggregate chat path — answers "total value", "how many funds", etc.
from the structured Statement table instead of vector retrieval.

Root cause this covers: aggregate questions ("What is the total value of my
portfolio?") cannot be answered by per-document RAG — no single chunk holds a
portfolio total, so the grounded LLM correctly refused (out_of_context). The fix
routes aggregate intents to a deterministic SQL aggregation over latest-per-fund
statements (same rule as GET /api/holdings, Property 9).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base, File, Statement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    s = factory()
    yield s
    s.close()
    engine.dispose()


def _seed(db: Session) -> None:
    """
    Seed 6 funds. Fund Alpha has TWO statements (Q2 + Q3 2025) → the latest
    (Q3, $4,945,000) must win; the older Q2 ($4,358,000) must NOT be counted.
    Expected portfolio total = 5,816,000 + 4,267,000 + 1,503,000 + 7,774,000
                             + 4,945,000 + 2,817,000 = 27,122,000.
    """
    specs = [
        ("Fund Zeta",    "2025-09-30", "5816000.00"),
        ("Fund Epsilon", "2025-09-30", "4267000.00"),
        ("Fund Gamma",   "2025-09-30", "1503000.00"),
        ("Fund Delta",   "2025-06-30", "7774000.00"),
        ("Fund Alpha",   "2025-06-30", "4358000.00"),  # older — must be excluded
        ("Fund Alpha",   "2025-09-30", "4945000.00"),  # latest — wins
        ("Fund Beta",    "2025-09-30", "2817000.00"),
    ]
    for i, (fund, sdate, val) in enumerate(specs, start=1):
        f = File(external_file_id=1000 + i, deal_id=1, file_name=f"{fund}_{sdate}.pdf",
                 status="extracted")
        db.add(f)
        db.flush()
        db.add(Statement(file_id=f.id, fund_name=fund, statement_date=sdate, current_value=val))
    db.commit()


EXPECTED_TOTAL = Decimal("27122000.00")
EXPECTED_FUNDS = 6


# ---------------------------------------------------------------------------
# parse_money
# ---------------------------------------------------------------------------

class TestParseMoney:
    def test_formats(self):
        from backend.rag.portfolio import parse_money
        assert parse_money("$5,816,000.00") == Decimal("5816000.00")
        assert parse_money("4267000.00") == Decimal("4267000.00")
        assert parse_money("  $1,503,000  ") == Decimal("1503000")
        assert parse_money("$0.00") == Decimal("0")

    def test_unparseable_returns_none(self):
        from backend.rag.portfolio import parse_money
        assert parse_money("N/A") is None
        assert parse_money("") is None
        assert parse_money(None) is None


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class TestClassifyQuery:
    @pytest.mark.parametrize("q", [
        "What is the total value of my portfolio?",
        "total portfolio value",
        "How much is my portfolio worth?",
        "what's the value of all my holdings",
    ])
    def test_portfolio_total_intent(self, q):
        from backend.rag.portfolio import classify_query
        assert classify_query(q) == "portfolio_total"

    @pytest.mark.parametrize("q", [
        "How many funds do I have?",
        "number of funds in my portfolio",
        "how many funds am I invested in",
    ])
    def test_fund_count_intent(self, q):
        from backend.rag.portfolio import classify_query
        assert classify_query(q) == "fund_count"

    @pytest.mark.parametrize("q", [
        "What was Fund Alpha's value in Q3?",
        "Summarize the Fund Beta commentary",
        "What is the NAV of Fund Gamma?",
        "When was the Fund Delta statement issued?",
    ])
    def test_non_aggregate_returns_none(self, q):
        from backend.rag.portfolio import classify_query
        assert classify_query(q) is None


# ---------------------------------------------------------------------------
# portfolio_summary — the aggregation itself
# ---------------------------------------------------------------------------

class TestPortfolioSummary:
    def test_total_is_latest_per_fund(self, db):
        from backend.rag.portfolio import portfolio_summary
        _seed(db)
        s = portfolio_summary(db)
        assert s["fund_count"] == EXPECTED_FUNDS
        assert s["total"] == EXPECTED_TOTAL
        # Alpha must reflect the Q3 (latest) value, not Q2.
        alpha = next(f for f in s["funds"] if f["fund_name"] == "Fund Alpha")
        assert alpha["value"] == Decimal("4945000.00")
        assert alpha["statement_date"] == "2025-09-30"

    def test_empty_db(self, db):
        from backend.rag.portfolio import portfolio_summary
        s = portfolio_summary(db)
        assert s["fund_count"] == 0
        assert s["total"] == Decimal("0")
        assert s["funds"] == []


# ---------------------------------------------------------------------------
# answer() routing — aggregate path is deterministic, never calls the LLM
# ---------------------------------------------------------------------------

class TestAnswerRouting:
    def test_total_query_uses_structured_path_not_llm(self, db, monkeypatch):
        """
        An aggregate query must be answered from SQL — NOT out_of_context, and
        WITHOUT invoking Gemini generate_text/embed_text.
        """
        _seed(db)

        import backend.llm.gemini_client as gem
        monkeypatch.setattr(gem, "generate_text",
                            lambda *a, **k: pytest.fail("LLM must not be called"))
        monkeypatch.setattr(gem, "embed_text",
                            lambda *a, **k: pytest.fail("embed must not be called"))

        from backend.rag.chat import answer
        r = answer("What is the total value of my portfolio?", db=db)

        assert r["out_of_context"] is False
        assert "27,122,000" in r["answer"]
        assert len(r["citations"]) == EXPECTED_FUNDS

    def test_fund_count_query(self, db, monkeypatch):
        _seed(db)
        import backend.llm.gemini_client as gem
        monkeypatch.setattr(gem, "generate_text",
                            lambda *a, **k: pytest.fail("LLM must not be called"))

        from backend.rag.chat import answer
        r = answer("How many funds do I have?", db=db)
        assert r["out_of_context"] is False
        assert "6" in r["answer"]

    def test_non_aggregate_query_still_uses_rag(self, db, monkeypatch):
        """A document-specific question must still flow through retrieve()/RAG."""
        called = {"retrieve": False}

        import backend.rag.chat as chat_mod

        def fake_retrieve(query, top_k=5, chroma_path=None):
            called["retrieve"] = True
            return []  # → OOC, but proves the RAG path was taken

        monkeypatch.setattr(chat_mod, "retrieve", fake_retrieve)

        r = chat_mod.answer("Summarize the Fund Beta commentary", db=db)
        assert called["retrieve"] is True
        assert r["out_of_context"] is True  # empty retrieval → honest OOC
