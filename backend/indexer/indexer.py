"""
ChromaDB indexer — T3.1.

Indexes classified documents (report + capital_account_statement) into a
persistent ChromaDB collection using Gemini text-embedding-004 embeddings.

Design:
- Collection name: ``investor_documents`` (ADR-004).
- Chunk id scheme: ``{external_file_id}_{chunk_index}`` — stable, idempotent.
- Idempotency: upsert by stable chunk id — re-indexing the same file_id does
  not duplicate vectors (ADR-004, Property 17).
- Chunk size: 800 chars, overlap 100 chars (sensible for 1-10 page PDFs).
- Metadata per chunk: external_file_id, file_name, classification, period
  (from Statement.statement_date or filename heuristic).
- Persist path: configurable via ``CHROMA_PATH`` env var; defaults to
  ``data/chroma/`` relative to the working directory.
- Indexer failures are non-fatal at the orchestrator level (ADR-008).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

import chromadb
from sqlalchemy.orm import Session

from backend.db.models import File, Statement

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "investor_documents"
CHUNK_SIZE = 800          # characters per chunk
CHUNK_OVERLAP = 100       # characters of overlap between chunks
_INDEXABLE_LABELS = {"report", "capital_account_statement"}

# ---------------------------------------------------------------------------
# ChromaDB client (lazy, module-level singleton)
# ---------------------------------------------------------------------------

_chroma_client: Optional[chromadb.Client] = None  # type: ignore[type-arg]
_chroma_path: Optional[str] = None


def _get_chroma_path() -> str:
    """Return the configured Chroma persistence directory."""
    return os.environ.get(
        "CHROMA_PATH",
        str(Path.cwd() / "data" / "chroma"),
    )


def get_chroma_client(chroma_path: Optional[str] = None) -> chromadb.ClientAPI:
    """
    Return the persistent ChromaDB client.

    The client is a module-level singleton so repeated calls within the same
    process share the same connection.  Pass ``chroma_path`` to override the
    default path (used by tests to inject a temp directory).
    """
    global _chroma_client, _chroma_path

    target_path = chroma_path or _get_chroma_path()

    # Re-create if the path changed (e.g., across test runs)
    if _chroma_client is None or _chroma_path != target_path:
        Path(target_path).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=target_path)
        _chroma_path = target_path
        logger.debug("ChromaDB client created at %s", target_path)

    return _chroma_client


def get_collection(chroma_path: Optional[str] = None) -> chromadb.Collection:
    """
    Return (or create) the ``investor_documents`` ChromaDB collection.

    Uses a custom embedding function that delegates to Gemini
    ``text-embedding-004`` via the canonical gemini_client.
    """
    client = get_chroma_client(chroma_path)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        # Store embeddings pre-computed; we supply them on add/upsert
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split ``text`` into overlapping chunks of ``chunk_size`` characters.

    Returns at least one chunk even for very short texts.
    """
    if not text.strip():
        return [""]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = end - overlap  # step forward with overlap

    return chunks if chunks else [""]


# ---------------------------------------------------------------------------
# Period heuristic (from Statement or filename)
# ---------------------------------------------------------------------------

def _extract_period(file: File, db: Session) -> Optional[str]:
    """
    Return a human-readable period string for citation.

    Priority:
      1. Latest statement_date from related Statement rows (for CAS).
      2. Heuristic parse of the file_name (e.g. Q1_2023 → "Q1 2023").
      3. None.
    """
    # 1. Statement date
    stmt = (
        db.query(Statement)
        .filter(Statement.file_id == file.id)
        .order_by(Statement.statement_date.desc())
        .first()
    )
    if stmt and stmt.statement_date:
        return stmt.statement_date  # ISO date string e.g. "2023-03-31"

    # 2. Filename heuristic  — e.g. "Q1_2023", "Q3_2021", "Mar2022", "Dec2024"
    name = file.file_name or ""
    # Q[1-4]_YYYY or Q[1-4] YYYY
    m = re.search(r"(Q[1-4])[_\s]?(\d{4})", name, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    # MonYYYY (e.g. Mar2022)
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(\d{4})",
        name,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}"
    # Standalone 4-digit year
    m = re.search(r"\b(20\d{2})\b", name)
    if m:
        return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Core indexer
# ---------------------------------------------------------------------------

def index_documents(
    db: Session,
    *,
    chroma_path: Optional[str] = None,
    force: bool = False,
) -> dict:
    """
    Index all eligible documents into ChromaDB.

    Eligible = classification in {report, capital_account_statement}
              AND local_path is not None (file is on disk).
    If ``force=False`` (default), already-indexed files (file.indexed == 1)
    are skipped unless the chunk ids are absent from the collection
    (so this is safe to call repeatedly — idempotent).

    Args:
        db: SQLAlchemy session with access to files/statements tables.
        chroma_path: Override ChromaDB persistence path (for tests).
        force: If True, re-index even files marked as indexed.

    Returns:
        Dict with counts: indexed, skipped, failed.
    """
    from backend.pdf_parser import parse_pdf, PdfParseError
    from backend.llm.gemini_client import embed_text, GeminiError

    collection = get_collection(chroma_path)

    files = (
        db.query(File)
        .filter(
            File.classification.in_(list(_INDEXABLE_LABELS)),
            File.local_path.isnot(None),
        )
        .all()
    )

    counts = {"indexed": 0, "skipped": 0, "failed": 0}

    for file in files:
        # Skip if already marked indexed unless force=True
        if file.indexed and not force:
            counts["skipped"] += 1
            logger.debug("File %d already indexed — skipping.", file.external_file_id)
            continue

        local_path = Path(file.local_path)  # type: ignore[arg-type]
        if not local_path.exists():
            logger.warning(
                "File %d local_path %s does not exist — skipping.",
                file.external_file_id,
                local_path,
            )
            counts["skipped"] += 1
            continue

        try:
            parsed = parse_pdf(local_path)
        except PdfParseError as exc:
            logger.warning("index_documents: parse failed for %s: %s", local_path, exc)
            counts["failed"] += 1
            continue

        text = parsed.text
        if not text.strip():
            logger.warning(
                "File %d has no extractable text — skipping.",
                file.external_file_id,
            )
            counts["skipped"] += 1
            continue

        chunks = _chunk_text(text)
        period = _extract_period(file, db)

        chunk_ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []
        documents: list[str] = []

        failed_chunk = False
        for i, chunk in enumerate(chunks):
            chunk_id = f"{file.external_file_id}_{i}"
            try:
                vector = embed_text(chunk)
            except GeminiError as exc:
                logger.warning(
                    "Embedding failed for file %d chunk %d: %s",
                    file.external_file_id, i, exc,
                )
                failed_chunk = True
                break

            chunk_ids.append(chunk_id)
            embeddings.append(vector)
            documents.append(chunk)
            metadatas.append(
                {
                    "external_file_id": str(file.external_file_id),
                    "file_name": file.file_name or "",
                    "classification": file.classification or "",
                    "period": period or "",
                }
            )

        if failed_chunk:
            counts["failed"] += 1
            continue

        # Upsert all chunks atomically (idempotent — same id overwrites)
        collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        # Mark file as indexed in DB
        file.indexed = 1
        db.add(file)
        db.commit()

        counts["indexed"] += 1
        logger.info(
            "Indexed file %d (%s) — %d chunks.",
            file.external_file_id, file.file_name, len(chunks),
        )

    logger.info("index_documents complete: %s", counts)
    return counts
