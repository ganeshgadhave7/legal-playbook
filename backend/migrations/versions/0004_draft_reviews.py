"""Persist human review decisions for generated drafts.

Revision ID: 0004_draft_reviews
Revises: 0003_cases_and_drafts
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004_draft_reviews"
down_revision: Union[str, Sequence[str], None] = "0003_cases_and_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "draft_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("draft_id", UUID(as_uuid=True), sa.ForeignKey("drafts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('approved', 'changes_requested', 'rejected')",
            name="ck_draft_reviews_decision",
        ),
    )
    op.create_index("ix_draft_reviews_draft_created", "draft_reviews", ["draft_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_draft_reviews_draft_created", table_name="draft_reviews")
    op.drop_table("draft_reviews")
