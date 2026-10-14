"""Promote existing superusers to admin role.

Revision ID: 0008
Revises: 0007
Create Date: 2025-10-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE is_superuser = true AND role != 'admin'")


def downgrade() -> None:
    pass
