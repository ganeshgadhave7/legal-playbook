"""Add a conservative local Voyage token usage ledger.

Revision ID: 0002_embedding_usage
Revises: 0001_source_documents
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_embedding_usage"
down_revision: Union[str, Sequence[str], None] = "0001_source_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "embedding_usage",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("tokens_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_embedding_usage_singleton_id"),
        sa.CheckConstraint("tokens_used >= 0", name="ck_embedding_usage_nonnegative"),
    )
    op.execute("INSERT INTO embedding_usage (id, tokens_used) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("embedding_usage")
