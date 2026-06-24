"""
Portfolio aggregation for chat — structured answers to corpus-wide questions.

Per-document RAG cannot answer aggregates like "total value of my portfolio":
no single chunk holds a portfolio total, so the grounded LLM correctly refuses.
This module routes such questions to a deterministic SQL aggregation over the
Statement table, using the SAME latest-per-fund rule as GET /api/holdings
(Property 9) so the chat total always matches the Holdings page.

Public API:
    classify_query(q)        -> "portfolio_total" | "fund_count" | None
    parse_money(s)           -> Decimal | None
    portfolio_summary(db)    -> {"total", "fund_count", "funds": [...]}
    answer_portfolio(q, intent, db=None) -> chat-answer dict | None
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

# Reuse the canonical latest-per-fund query (single source of truth, Property 9).
from backend.api.routers.holdings import _HOLDINGS_SQL

_OOC_NONE = None


# ---------------------------------------------------------------------------
# Money parsing
# ---------------------------------------------------------------------------

def parse_money(value: Optional[str]) -> Optional[Decimal]:
    """'$5,816,000.00' / '4267000.00' → Decimal. None if unparseable/empty."""
    if value is None:
        return None
    cleaned = re.sub(r"[,$\s]", "", str(value))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _fmt_money(d: Decimal) -> str:
    return f"${d:,.2f}"


# ---------------------------------------------------------------------------
# Intent classification (conservative — must not hijack document questions)
# ---------------------------------------------------------------------------

# A specific fund name in the query means it's document-scoped, not aggregate.
_FUND_MENTION = re.compile(r"\bfund\s+(alpha|beta|gamma|delta|epsilon|zeta|eta|theta)\b", re.I)
_PORTFOLIO_WORD = re.compile(r"\b(portfolio|holdings|investments?|all (?:my )?funds|everything)\b", re.I)
_VALUE_WORD = re.compile(r"\b(total|value|worth|sum|net asset value|nav|aum)\b", re.I)
_COUNT_PHRASE = re.compile(r"\b(how many|number of|count of)\b.*\bfunds?\b", re.I)


def classify_query(query: str) -> Optional[str]:
    """
    Detect corpus-wide aggregate intent. Returns:
      "fund_count"      — "how many funds do I have"
      "portfolio_total" — "total value of my portfolio"
      None              — anything document/fund-specific (→ normal RAG)
    """
    q = query.strip()

    # Fund-specific questions are never aggregates.
    if _FUND_MENTION.search(q):
        return _OOC_NONE

    if _COUNT_PHRASE.search(q):
        return "fund_count"

    if _PORTFOLIO_WORD.search(q) and _VALUE_WORD.search(q):
        return "portfolio_total"

    return _OOC_NONE


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def portfolio_summary(db: Session) -> dict:
    """
    Latest statement per fund + parsed values + portfolio total.

    Returns:
        {
          "total": Decimal,        # sum of parseable current_values
          "fund_count": int,
          "funds": [{
              "fund_name": str, "value": Decimal|None, "statement_date": str,
              "external_file_id": str, "file_name": str,
          }],
        }
    """
    from backend.db.models import File

    rows = db.execute(_HOLDINGS_SQL).fetchall()  # fund_name, current_value, statement_date, file_id

    file_ids = [r.file_id for r in rows]
    files = {
        f.id: f
        for f in db.query(File).filter(File.id.in_(file_ids)).all()
    } if file_ids else {}

    funds: list[dict] = []
    total = Decimal("0")
    for r in rows:
        val = parse_money(r.current_value)
        if val is not None:
            total += val
        f = files.get(r.file_id)
        funds.append({
            "fund_name": r.fund_name,
            "value": val,
            "statement_date": r.statement_date,
            "external_file_id": str(f.external_file_id) if f else "",
            "file_name": f.file_name if f else "",
        })

    return {"total": total, "fund_count": len(rows), "funds": funds}


# ---------------------------------------------------------------------------
# Answer builder
# ---------------------------------------------------------------------------

def _citations(funds: list[dict]) -> list[dict]:
    out: list[dict] = []
    for f in funds:
        if f["external_file_id"]:
            out.append({
                "file_id": f["external_file_id"],
                "file_name": f["file_name"],
                "period": f["statement_date"] or None,
            })
    return out


def answer_portfolio(query: str, intent: str, db: Optional[Session] = None) -> Optional[dict]:
    """
    Build a deterministic chat answer for an aggregate `intent`.

    Returns a dict shaped like rag.chat.answer() output, or None if there are no
    statements yet (caller falls back to the normal RAG/OOC path).
    """
    own_session = db is None
    if own_session:
        from backend.db.session import get_session_factory
        db = get_session_factory()()

    try:
        summary = portfolio_summary(db)
        if summary["fund_count"] == 0:
            return None  # nothing extracted yet → let RAG/OOC handle it honestly

        funds = summary["funds"]
        breakdown = "; ".join(
            f"{f['fund_name']}: {_fmt_money(f['value'])}" if f["value"] is not None
            else f"{f['fund_name']}: value unavailable"
            for f in funds
        )

        if intent == "fund_count":
            names = ", ".join(f["fund_name"] for f in funds)
            answer_text = (
                f"You hold {summary['fund_count']} fund(s): {names}."
            )
        else:  # portfolio_total
            unparsed = [f["fund_name"] for f in funds if f["value"] is None]
            note = (
                f" (Note: value could not be read for {', '.join(unparsed)}; "
                "they are excluded from the total.)"
                if unparsed else ""
            )
            answer_text = (
                f"Your portfolio totals {_fmt_money(summary['total'])} across "
                f"{summary['fund_count']} fund(s), based on each fund's most recent "
                f"capital account statement. Breakdown — {breakdown}.{note}"
            )

        return {
            "answer": answer_text,
            "citations": _citations(funds),
            "out_of_context": False,
        }
    finally:
        if own_session:
            db.close()
