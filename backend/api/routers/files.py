"""
Files router — T2.x.

GET /api/files         → list[FileRecord]  (bare array)
GET /api/files/{id}/download → FileResponse (PDF)
"""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from backend.db.session import get_db
from backend.db.models import File, Statement

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class FileRecord(BaseModel):
    file_id: str
    file_name: str
    doc_type: Literal["capital_account_statement", "report", "other"]
    classification_confidence: float
    low_confidence: bool
    period: str | None
    fund_name: str | None
    uploaded_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_DOC_TYPES = {"capital_account_statement", "report", "other"}


def _to_doc_type(classification: str | None) -> Literal["capital_account_statement", "report", "other"]:
    if classification in _VALID_DOC_TYPES:
        return classification  # type: ignore[return-value]
    return "other"


def _latest_statement(statements: list[Statement]) -> Statement | None:
    """Return the statement with the lexicographically greatest statement_date."""
    if not statements:
        return None
    return max(statements, key=lambda s: s.statement_date)


def _map_file(file: File) -> FileRecord:
    latest = _latest_statement(file.statements)

    confidence = file.confidence if file.confidence is not None else 0.0
    low_conf = bool(file.low_confidence) or (file.confidence is not None and file.confidence < 0.75)

    return FileRecord(
        file_id=str(file.id),
        file_name=file.file_name,
        doc_type=_to_doc_type(file.classification),
        classification_confidence=confidence,
        low_confidence=low_conf,
        period=latest.statement_date if latest else None,
        fund_name=latest.fund_name if latest else None,
        uploaded_at=file.download_ts or file.created_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/files", response_model=list[FileRecord], tags=["files"])
def list_files(db: Session = Depends(get_db)) -> Any:
    """
    Return all known files with their classification and latest statement info.
    """
    files = (
        db.query(File)
        .options(joinedload(File.statements))
        .order_by(File.id)
        .all()
    )
    return [_map_file(f) for f in files]


@router.get("/files/{file_id}/download", tags=["files"])
def download_file(file_id: str, db: Session = Depends(get_db)) -> Any:
    """
    Stream a PDF file to the client.
    """
    try:
        fid = int(file_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

    file = db.query(File).filter(File.id == fid).first()
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    if not file.local_path or not os.path.isfile(file.local_path):
        raise HTTPException(status_code=404, detail="File not available")

    return FileResponse(
        file.local_path,
        media_type="application/pdf",
        filename=file.file_name,
    )
