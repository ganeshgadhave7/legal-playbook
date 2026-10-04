"""Persist vendor onboarding cases, drafts, and source citations.

Revision ID: 0003_cases_and_drafts
Revises: 0002_embedding_usage
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003_cases_and_drafts"
down_revision: Union[str, Sequence[str], None] = "0002_embedding_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("playbook_key", sa.Text(), nullable=False),
        sa.Column("playbook_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("intake_answers", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('submitted', 'processing', 'draft_pending_review', 'changes_requested', 'approved', 'rejected', 'failed')",
            name="ck_cases_status",
        ),
    )
    op.create_index("ix_cases_status_created", "cases", ["status", "created_at"])

    op.create_table(
        "drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version > 0", name="ck_drafts_positive_version"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'changes_requested', 'approved', 'rejected', 'superseded')",
            name="ck_drafts_status",
        ),
        sa.UniqueConstraint("case_id", "version", name="uq_drafts_case_version"),
    )
    op.create_index("ix_drafts_case_status", "drafts", ["case_id", "status"])

    op.create_table(
        "draft_citations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("draft_id", UUID(as_uuid=True), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.CheckConstraint("rank > 0", name="ck_draft_citations_positive_rank"),
        sa.CheckConstraint("similarity >= -1 AND similarity <= 1", name="ck_draft_citations_similarity_range"),
        sa.UniqueConstraint("draft_id", "chunk_id", name="uq_draft_citations_draft_chunk"),
    )
    op.create_index("ix_draft_citations_draft_rank", "draft_citations", ["draft_id", "rank"])


def downgrade() -> None:
    op.drop_index("ix_draft_citations_draft_rank", table_name="draft_citations")
    op.drop_table("draft_citations")
    op.drop_index("ix_drafts_case_status", table_name="drafts")
    op.drop_table("drafts")
    op.drop_index("ix_cases_status_created", table_name="cases")
    op.drop_table("cases")
