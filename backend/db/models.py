"""
SQLAlchemy ORM models.

Schema follows design.md §Data Models with ADR-007 override:
  - files.external_file_id INTEGER UNIQUE NOT NULL  (idempotency key)
  - files.file_url is NOT a uniqueness key (presigned URL rotates)

Classification labels and statuses are enforced at the DB level via CHECK constraints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    REAL,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base  # noqa: F401 — declarative base


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class File(Base):
    """
    Tracks every discovered portal file through its lifecycle.

    Key constraint: UNIQUE(external_file_id) — ADR-007, Property 13.
    file_url is stored for download but is NOT a uniqueness key (presigned, rotates).
    """
    __tablename__ = "files"

    __table_args__ = (
        UniqueConstraint("external_file_id", name="uq_files_external_file_id"),
        CheckConstraint(
            "status IN ('pending', 'downloaded', 'extracted', 'failed')",
            name="ck_files_status",
        ),
        CheckConstraint(
            "classification IS NULL OR classification IN ("
            "'capital_account_statement', 'report', 'other', 'unclassified')",
            name="ck_files_classification",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ADR-007: stable integer file id from the portal JSON API — idempotency key
    external_file_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )

    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Portal's own document_type label — eval ground-truth only (NOT our classification)
    portal_doc_type: Mapped[str | None] = mapped_column(Text, nullable=True)

    file_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Presigned S3 URL — rotates every ~1 h; stored for reference, not as a key
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SHA-256 hex digest of file content (integrity check)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Absolute or relative local path on disk after download
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISO 8601 UTC timestamp of successful download
    download_ts: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle status — must be one of the four values above
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default="pending",
    )

    # Our classification (NOT portal_doc_type)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classifier confidence [0.0, 1.0]
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)

    # True (1) when confidence < 0.75
    low_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Human-readable extraction failure reason
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 0 = not indexed in ChromaDB; 1 = indexed
    indexed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ISO 8601 UTC creation timestamp
    created_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=_utcnow,
        server_default=func.datetime("now"),
    )

    # Relationship: a file can have zero or more extracted statements
    statements: Mapped[list["Statement"]] = relationship(
        "Statement",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<File id={self.id} external_file_id={self.external_file_id} "
            f"name={self.file_name!r} status={self.status!r}>"
        )


class Statement(Base):
    """
    Structured data extracted from a capital account statement PDF.

    Required fields: fund_name, statement_date, current_value.
    Atomicity: either all three are present or the row does not exist (enforced in extractor).
    """
    __tablename__ = "statements"

    __table_args__ = (
        # Index for the holdings query: latest statement per fund
        Index("idx_statements_fund_date", "fund_name", "statement_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FK to files.id — CASCADE DELETE so orphan statements are cleaned up
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )

    fund_name: Mapped[str] = mapped_column(Text, nullable=False)

    # ISO 8601 date string (YYYY-MM-DD)
    statement_date: Mapped[str] = mapped_column(Text, nullable=False)

    # Stored as TEXT to preserve decimal precision (e.g. "1234567.89")
    current_value: Mapped[str] = mapped_column(Text, nullable=False)

    file: Mapped["File"] = relationship("File", back_populates="statements")

    def __repr__(self) -> str:
        return (
            f"<Statement id={self.id} file_id={self.file_id} "
            f"fund={self.fund_name!r} date={self.statement_date!r} "
            f"value={self.current_value!r}>"
        )
