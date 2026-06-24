"""0001_init — create files and statements tables.

Revision ID: 0001_init
Revises:
Create Date: 2026-06-24

ADR-007: idempotency key is external_file_id (UNIQUE) — NOT (portal_url, file_name).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # files table
    # UNIQUE(external_file_id) declared inline so it works on SQLite.
    # ------------------------------------------------------------------
    op.create_table(
        "files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # ADR-007: stable integer portal file id — idempotency key (Property 13)
        # unique=False here because the named UniqueConstraint below is the canonical one
        sa.Column("external_file_id", sa.Integer, nullable=False),
        sa.Column("deal_id", sa.Integer, nullable=True),
        # Portal's own label — eval ground-truth only, NOT our classification
        sa.Column("portal_doc_type", sa.Text, nullable=True),
        sa.Column("file_name", sa.Text, nullable=False),
        # Presigned S3 URL — rotates; stored for reference only, NOT a key
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("content_hash", sa.Text, nullable=True),
        sa.Column("local_path", sa.Text, nullable=True),
        sa.Column("download_ts", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("classification", sa.Text, nullable=True),
        sa.Column("confidence", sa.REAL, nullable=True),
        sa.Column("low_confidence", sa.Integer, nullable=True),
        sa.Column("extraction_error", sa.Text, nullable=True),
        sa.Column("indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.Text,
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        # CHECK constraints for status and classification
        sa.CheckConstraint(
            "status IN ('pending', 'downloaded', 'extracted', 'failed')",
            name="ck_files_status",
        ),
        sa.CheckConstraint(
            "classification IS NULL OR classification IN ("
            "'capital_account_statement', 'report', 'other', 'unclassified')",
            name="ck_files_classification",
        ),
        # UNIQUE constraint on external_file_id — inline for SQLite compatibility
        sa.UniqueConstraint("external_file_id", name="uq_files_external_file_id"),
    )

    # ------------------------------------------------------------------
    # statements table
    # ------------------------------------------------------------------
    op.create_table(
        "statements",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "file_id",
            sa.Integer,
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fund_name", sa.Text, nullable=False),
        # ISO 8601 date string YYYY-MM-DD
        sa.Column("statement_date", sa.Text, nullable=False),
        # Stored as TEXT to preserve decimal precision
        sa.Column("current_value", sa.Text, nullable=False),
    )

    # Index for holdings query: latest statement per fund
    op.create_index(
        "idx_statements_fund_date",
        "statements",
        ["fund_name", "statement_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_statements_fund_date", table_name="statements")
    op.drop_table("statements")
    op.drop_table("files")
