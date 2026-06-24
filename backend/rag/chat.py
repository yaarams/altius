"""
Retrieval-augmented generation chat — T3.2.

Provides two public functions:

    retrieve(query, top_k, chroma_path) -> list[dict]
        ChromaDB similarity search; top_k capped at 20 (ADR-004 / Property 17).

    answer(query, top_k, chroma_path) -> dict
        Build grounded prompt → Gemini generation → {answer, citations, out_of_context}.

Design:
- Citations carry {file_id, file_name, period} matching the frontend Citation type.
- Out-of-corpus honesty (Property 16): if no documents retrieved or all distances
  exceed OOC_DISTANCE_THRESHOLD, return a "not found" answer with empty citations
  and out_of_context=True — never hallucinate.
- The OOC threshold is tuned for cosine distance (ChromaDB cosine space):
  distance=0 → identical; distance=1 → orthogonal.  Anything above 0.8 is treated
  as "not relevant" (effectively no match).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_K_CAP = 20                  # hard cap — Property 17
OOC_DISTANCE_THRESHOLD = 0.8    # cosine distance above which we declare OOC

_RAG_SYSTEM_PROMPT = (
    "You are a financial assistant that answers questions about investor documents. "
    "Answer ONLY from the provided document excerpts (context). "
    "Be concise and factual. "
    "If the context does not contain enough information to answer the question, "
    "say exactly: 'I could not find this information in the indexed documents.' "
    "Never fabricate financial data, fund names, dates, or values not present in the context."
)

_OOC_ANSWER = "I could not find this information in the indexed documents."

# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


def retrieve(
    query: str,
    top_k: int = 5,
    chroma_path: Optional[str] = None,
) -> list[dict]:
    """
    Embed ``query`` and perform a ChromaDB similarity search.

    Args:
        query: Natural-language question.
        top_k: Number of results to request.  Capped at TOP_K_CAP (20).
        chroma_path: Override ChromaDB path (for tests).

    Returns:
        List of result dicts, each with keys:
            id, document, metadata, distance
        Ordered by ascending cosine distance (most similar first).
        Empty list if the collection has no documents.
    """
    from backend.llm.gemini_client import embed_text, GeminiError
    from backend.indexer.indexer import get_collection

    # Enforce hard cap
    effective_k = min(top_k, TOP_K_CAP)

    collection = get_collection(chroma_path)
    if collection.count() == 0:
        logger.debug("retrieve: collection is empty — returning []")
        return []

    try:
        query_embedding = embed_text(query)
    except GeminiError as exc:
        logger.warning("retrieve: embed_text failed: %s", exc)
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(effective_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    # Flatten into a list of dicts
    out: list[dict] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
        out.append(
            {
                "id": chunk_id,
                "document": doc,
                "metadata": meta or {},
                "distance": dist,
            }
        )

    return out


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------


def answer(
    query: str,
    top_k: int = 5,
    chroma_path: Optional[str] = None,
) -> dict:
    """
    Retrieve relevant chunks and generate a grounded answer.

    Returns a dict matching the frontend ChatResponse type:
        {
            "answer": str,
            "citations": [{"file_id": str, "file_name": str, "period": str|None}],
            "out_of_context": bool,
        }

    Out-of-corpus behaviour (Property 16):
        If no chunks are retrieved, or all chunks have cosine distance ≥
        OOC_DISTANCE_THRESHOLD, returns:
            answer = _OOC_ANSWER
            citations = []
            out_of_context = True

    Citations are deduplicated by external_file_id and preserve order of relevance.
    """
    from backend.llm.gemini_client import generate_text, GeminiError

    chunks = retrieve(query, top_k=top_k, chroma_path=chroma_path)

    # Filter by relevance
    relevant = [c for c in chunks if c["distance"] < OOC_DISTANCE_THRESHOLD]

    if not relevant:
        logger.info("answer: no relevant chunks found for query %r (OOC)", query[:80])
        return {
            "answer": _OOC_ANSWER,
            "citations": [],
            "out_of_context": True,
        }

    # Build grounded context
    context_parts: list[str] = []
    for i, chunk in enumerate(relevant, start=1):
        meta = chunk["metadata"]
        header = f"[{i}] {meta.get('file_name', 'unknown')} (period: {meta.get('period', 'unknown')})"
        context_parts.append(f"{header}\n{chunk['document']}")

    context_text = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"Context documents:\n\n{context_text}\n\n"
        f"---\n\nQuestion: {query}\n\n"
        "Answer based only on the context above."
    )

    try:
        generated_answer = generate_text(prompt, system_prompt=_RAG_SYSTEM_PROMPT)
    except GeminiError as exc:
        logger.warning("answer: generate_text failed: %s", exc)
        generated_answer = _OOC_ANSWER

    # Detect if Gemini itself said it couldn't find info
    out_of_context = _OOC_ANSWER.lower() in generated_answer.lower()

    # Build deduplicated citations (order by first appearance)
    seen_file_ids: set[str] = set()
    citations: list[dict] = []
    for chunk in relevant:
        meta = chunk["metadata"]
        file_id = meta.get("external_file_id", "")
        if file_id and file_id not in seen_file_ids:
            seen_file_ids.add(file_id)
            period_raw = meta.get("period", "") or None
            citations.append(
                {
                    "file_id": file_id,
                    "file_name": meta.get("file_name", ""),
                    "period": period_raw if period_raw else None,
                }
            )

    if out_of_context:
        citations = []

    return {
        "answer": generated_answer,
        "citations": citations,
        "out_of_context": out_of_context,
    }
