"""
Holdings router — T2.4.

GET /api/holdings → latest statement per fund.

Uses a single SQL query with:
  - lower(trim(fund_name)) normalization
  - MAX(statement_date) for latest
  - MAX(id) as tie-breaker when dates are equal

Property 9: exactly one row per normalized fund name, latest date, highest-id tie-break.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.session import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class HoldingRow(BaseModel):
    fund_name: str
    current_value: str          # "$1,234,567.89"
    statement_date: str         # "March 31, 2025"
    file_id: int


class HoldingsResponse(BaseModel):
    holdings: list[HoldingRow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_currency(value_str: str) -> str:
    """'1234567.89' → '$1,234,567.89'"""
    try:
        d = Decimal(value_str)
        return f"${d:,.2f}"
    except Exception:
        return value_str  # return as-is if unparseable


def _format_date(date_str: str) -> str:
    """'2025-09-30' → 'September 30, 2025'"""
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return date_str  # return as-is if unparseable


# ---------------------------------------------------------------------------
# Latest-per-fund SQL (design.md §Data Models)
# ---------------------------------------------------------------------------

_HOLDINGS_SQL = text("""
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
""")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/holdings", response_model=HoldingsResponse, tags=["holdings"])
def get_holdings(db: Session = Depends(get_db)) -> Any:
    """
    Return the latest capital account statement value per fund.

    Empty when no statements have been extracted yet.
    """
    rows = db.execute(_HOLDINGS_SQL).fetchall()

    holdings = [
        HoldingRow(
            fund_name=row.fund_name,
            current_value=_format_currency(row.current_value),
            statement_date=_format_date(row.statement_date),
            file_id=row.file_id,
        )
        for row in rows
    ]

    return HoldingsResponse(holdings=holdings)
