"""
Chat router — T3.2.

POST /api/chat  →  {answer, citations, out_of_context}

Request body:  ChatRequest  { query: str }
Response body: ChatResponse { answer: str, citations: [{file_id, file_name, period}], out_of_context: bool }

Shape matches frontend types.ts exactly (Citation.file_id, Citation.file_name, Citation.period).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models — must match frontend types.ts
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., description="Natural-language question about investor documents.")


class Citation(BaseModel):
    file_id: str
    file_name: str
    period: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    out_of_context: bool


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def _external_to_db_id_map(db: Session, external_ids: list[str]) -> dict[str, str]:
    """
    Map ChromaDB chunk metadata ``external_file_id`` → ``File.id`` (as strings).

    RAG citations carry the portal ``external_file_id`` (the indexer's chunk-id
    key), but the frontend's download route resolves ``File.id`` (see
    GET /api/files/{id}/download and FileRecord.file_id = str(File.id)). Without
    this translation citation links 404. Missing/non-integer ids are skipped and
    fall back to the original value.
    """
    from backend.db.models import File

    int_ids: list[int] = []
    for ext in external_ids:
        try:
            int_ids.append(int(ext))
        except (TypeError, ValueError):
            continue
    if not int_ids:
        return {}

    rows = (
        db.query(File.id, File.external_file_id)
        .filter(File.external_file_id.in_(int_ids))
        .all()
    )
    return {str(ext): str(db_id) for db_id, ext in rows}


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def post_chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """
    Answer a question grounded in the indexed investor documents.

    Returns an honest 'not found' response with empty citations when the
    question falls outside the indexed corpus (Property 16 — OOC honesty).
    """
    from backend.rag.chat import answer as rag_answer

    result = rag_answer(req.query)

    id_map = _external_to_db_id_map(
        db, [c["file_id"] for c in result["citations"]]
    )

    return ChatResponse(
        answer=result["answer"],
        citations=[
            Citation(
                # Translate external_file_id → File.id so citation links resolve
                # against /api/files/{id}/download; fall back to the raw id.
                file_id=id_map.get(c["file_id"], c["file_id"]),
                file_name=c["file_name"],
                period=c.get("period"),
            )
            for c in result["citations"]
        ],
        out_of_context=result["out_of_context"],
    )
