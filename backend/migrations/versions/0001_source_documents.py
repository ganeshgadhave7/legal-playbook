"""Create initial approved-source RAG tables.

Revision ID: 0001_source_documents
Revises:
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0001_source_documents"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extension is installed at database scope; this operation requires suitable DB privileges.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("document_code", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="uploaded"),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("fictional", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'pending_review', 'approved', 'indexing', 'ready', 'rejected', 'archived', 'failed')",
            name="ck_source_documents_status",
        ),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_source_documents_positive_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_source_documents_sha256_length"),
        sa.UniqueConstraint("document_code", "version", name="uq_source_documents_code_version"),
    )
    op.create_index("ix_source_documents_status", "source_documents", ["status"])
    op.create_index("ix_source_documents_department_type", "source_documents", ["department", "document_type"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "source_document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_nonnegative_index"),
        sa.CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_document_chunks_positive_page"),
        sa.UniqueConstraint("source_document_id", "chunk_index", name="uq_document_chunks_source_index"),
    )
    op.create_index("ix_document_chunks_source_document_id", "document_chunks", ["source_document_id"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "source_document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('approved', 'changes_requested', 'rejected')",
            name="ck_approval_decisions_value",
        ),
    )
    op.create_index("ix_approval_decisions_source_document_id", "approval_decisions", ["source_document_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_decisions_source_document_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")

    op.drop_index("ix_document_chunks_source_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_source_documents_department_type", table_name="source_documents")
    op.drop_index("ix_source_documents_status", table_name="source_documents")
    op.drop_table("source_documents")

    # Deliberately leave the shared vector extension installed; it may be used elsewhere.
