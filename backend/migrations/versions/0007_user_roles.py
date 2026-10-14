"""Add role column to users table.

Revision ID: 0007
Revises: 0006
Create Date: 2025-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["admin", "editor", "user", "viewer"]


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.create_check_constraint("ck_users_role", "users", sa.text(f"role IN {tuple(ROLES)}"))


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
