"""add playbooks table

Revision ID: 64125eabffb3
Revises: 0004_draft_reviews
Create Date: 2026-10-03 12:13:01.352071
"""
import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = '64125eabffb3'
down_revision: Union[str, Sequence[str], None] = '0004_draft_reviews'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("intake_questions", JSONB(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_playbooks_status",
        ),
        sa.UniqueConstraint("key", "version", name="uq_playbooks_key_version"),
    )
    op.create_index("ix_playbooks_key", "playbooks", ["key"])
    op.create_index("ix_playbooks_status", "playbooks", ["status"])

    # Link cases to the playbook table.
    op.add_column(
        "cases",
        sa.Column("playbook_id", UUID(as_uuid=True), sa.ForeignKey("playbooks.id"), nullable=True),
    )
    op.create_index("ix_cases_playbook_id", "cases", ["playbook_id"])

    # Seed the existing Vendor Onboarding Playbook so the demo keeps working.
    vendor_playbook_id = str(uuid4())
    intake_questions_json = json.dumps([
        {
            "key": "vendor_name",
            "label": "Vendor legal name",
            "type": "text",
            "required": True,
            "validation": {"min_length": 1, "max_length": 250},
        },
        {
            "key": "service_description",
            "label": "Service description",
            "type": "text",
            "required": True,
            "validation": {"min_length": 10, "max_length": 3000},
        },
        {
            "key": "annual_spend_usd",
            "label": "Estimated annual spend (USD)",
            "type": "number",
            "required": True,
            "validation": {"gt": 0, "le": 1000000000},
        },
        {
            "key": "handles_personal_data",
            "label": "Processes personal data",
            "type": "boolean",
            "required": True,
        },
        {
            "key": "requires_system_access",
            "label": "Requires system access",
            "type": "boolean",
            "required": True,
        },
        {
            "key": "uses_subcontractors",
            "label": "Uses subcontractors",
            "type": "boolean",
            "required": True,
        },
        {
            "key": "business_criticality",
            "label": "Business criticality",
            "type": "select",
            "required": True,
            "options": ["low", "medium", "high", "critical"],
        },
    ])
    prompt_template = (
        "You are an AI assistant for Acme Technologies LLC legal operations. "
        "Produce a vendor onboarding checklist and risk summary strictly grounded "
        "in the approved policy passages provided.\n\n"
        "Rules:\n"
        "1. Use only facts that appear in the retrieved source passages.\n"
        "2. If the intake raises a risk but no source passage supports the required action, "
        "   add the item to missing_information instead of inventing a requirement.\n"
        "3. Keep the tone professional and concise.\n"
        "4. The output is a draft for qualified human review, not a final legal determination.\n\n"
        "Respond with valid JSON only."
    )

    op.execute(
        sa.text(
            """
            INSERT INTO playbooks (
                id, key, version, title, department, description,
                status, intake_questions, prompt_template
            ) VALUES (
                CAST(:id AS uuid),
                'vendor_onboarding',
                '1',
                'Vendor Onboarding',
                'Procurement',
                'Generate a cited onboarding checklist and risk summary for new vendors.',
                'published',
                CAST(:intake_questions AS jsonb),
                CAST(:prompt_template AS text)
            )
            """
        ).bindparams(
            id=vendor_playbook_id,
            intake_questions=intake_questions_json,
            prompt_template=prompt_template,
        )
    )


def downgrade() -> None:
    op.drop_index("ix_cases_playbook_id", table_name="cases")
    op.drop_column("cases", "playbook_id")

    op.drop_index("ix_playbooks_status", table_name="playbooks")
    op.drop_index("ix_playbooks_key", table_name="playbooks")
    op.drop_table("playbooks")
