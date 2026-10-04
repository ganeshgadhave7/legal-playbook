"""Explicit, versioned fictional playbook rules evaluated deterministically."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class ConditionalRule:
    key: str
    playbook_version: str
    intake_field: str
    operator: Literal["gt", "gte", "lt", "lte", "eq"]
    threshold: Decimal
    unit: str
    condition_label: str
    action: str
    source_document_code: str
    source_version: str
    source_section: str
    policy_scope: str


# This rule is synthetic demo configuration authored from the fictional source.
# The source text says invoice totals above $10,000 trigger review; it does not
# establish that a vendor's annual spend has the same meaning. The scope is
# therefore deliberately `invoice_amount_usd`, not `annual_spend_usd`.
VENDOR_ONBOARDING_RULES: tuple[ConditionalRule, ...] = (
    ConditionalRule(
        key="invoice-human-review-threshold",
        playbook_version="1",
        intake_field="invoice_amount_usd",
        operator="gt",
        threshold=Decimal("10000"),
        unit="USD",
        condition_label="invoice amount exceeds $10,000",
        action="Require human-in-the-loop review for the invoice.",
        source_document_code="PROC-POL-001",
        source_version="1.0",
        source_section="4. Approval",
        policy_scope="invoice_amount_usd",
    ),
)


def evaluate_operator(actual: Decimal, operator: str, threshold: Decimal) -> bool:
    if operator == "gt":
        return actual > threshold
    if operator == "gte":
        return actual >= threshold
    if operator == "lt":
        return actual < threshold
    if operator == "lte":
        return actual <= threshold
    if operator == "eq":
        return actual == threshold
    raise ValueError(f"Unsupported playbook-rule operator: {operator}")
