"""
Chat router — T3.2.

POST /api/chat  →  {answer, citations, out_of_context}

Request body:  ChatRequest  { query: str }
Response body: ChatResponse { answer: str, citations: [{file_id, file_name, period}], out_of_context: bool }

Shape matches frontend types.ts exactly (Citation.file_id, Citation.file_name, Citation.period).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

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

@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def post_chat(req: ChatRequest) -> ChatResponse:
    """
    Answer a question grounded in the indexed investor documents.

    Returns an honest 'not found' response with empty citations when the
    question falls outside the indexed corpus (Property 16 — OOC honesty).
    """
    from backend.rag.chat import answer as rag_answer

    result = rag_answer(req.query)

    return ChatResponse(
        answer=result["answer"],
        citations=[
            Citation(
                file_id=c["file_id"],
                file_name=c["file_name"],
                period=c.get("period"),
            )
            for c in result["citations"]
        ],
        out_of_context=result["out_of_context"],
    )
