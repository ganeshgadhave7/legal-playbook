"""Allow pending_review status in cases table.

Revision ID: 0012
Revises: 0011
Create Date: 2025-10-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_cases_status", "cases", type_="check")
    op.create_check_constraint(
        "ck_cases_status",
        "cases",
        "status IN ('submitted', 'processing', 'draft_pending_review', 'pending_review', 'changes_requested', 'approved', 'rejected', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cases_status", "cases", type_="check")
    op.create_check_constraint(
        "ck_cases_status",
        "cases",
        "status IN ('submitted', 'processing', 'draft_pending_review', 'changes_requested', 'approved', 'rejected', 'failed')",
    )
