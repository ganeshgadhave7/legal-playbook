"""Explicit, versioned fictional playbook rules evaluated deterministically."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal


@dataclass(frozen=True)
class ConditionalRule:
    """A deterministic rule tied to a specific playbook."""

    key: str
    playbook_key: str
    playbook_version: str
    intake_field: str
    operator: Literal["gt", "gte", "lt", "lte", "eq"]
    threshold: Decimal
    unit: str
    condition_label: str
    action: str
    action_keywords: tuple[str, ...]
    source_document_code: str
    source_version: str
    source_section: str
    policy_scope: str


def evaluate_operator(actual: Decimal, operator: str, threshold: Decimal) -> bool:
    """Evaluate a numeric comparison."""
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


# ---------------------------------------------------------------------------
# Static rule registry. In production these can be moved to a database table
# linked to playbooks.
# ---------------------------------------------------------------------------
VENDOR_ONBOARDING_RULES: tuple[ConditionalRule, ...] = (
    ConditionalRule(
        key="invoice-human-review-threshold",
        playbook_key="vendor_onboarding",
        playbook_version="1",
        intake_field="annual_spend_usd",
        operator="gt",
        threshold=Decimal("10000"),
        unit="USD",
        condition_label="annual spend exceeds $10,000",
        action="Require human-in-the-loop review for the vendor engagement.",
        action_keywords=("human review", "human-in-the-loop"),
        source_document_code="PROC-POL-001",
        source_version="1.0",
        source_section="4. Approval",
        policy_scope="annual_spend_usd",
    ),
)


ALL_RULES: tuple[ConditionalRule, ...] = (*VENDOR_ONBOARDING_RULES,)


def get_rules_for_playbook(playbook_key: str, playbook_version: str | None = None) -> tuple[ConditionalRule, ...]:
    """Return deterministic rules for a playbook, optionally filtered by version."""
    rules = [r for r in ALL_RULES if r.playbook_key == playbook_key]
    if playbook_version is not None:
        rules = [r for r in rules if r.playbook_version == playbook_version]
    return tuple(rules)
