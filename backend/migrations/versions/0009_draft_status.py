"""Allow draft_pending_review status in drafts table.

Revision ID: 0009
Revises: 0008
Create Date: 2025-10-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_drafts_status", "drafts", type_="check")
    op.create_check_constraint(
        "ck_drafts_status",
        "drafts",
        "status IN ('draft_pending_review', 'pending_review', 'changes_requested', 'approved', 'rejected', 'superseded')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_drafts_status", "drafts", type_="check")
    op.create_check_constraint(
        "ck_drafts_status",
        "drafts",
        "status IN ('pending_review', 'changes_requested', 'approved', 'rejected', 'superseded')",
    )
