"""Consistency checker: enforces deterministic playbook rules against drafts."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from app.workflows.playbook_rules import ConditionalRule, evaluate_operator, get_rules_for_playbook

logger = logging.getLogger(__name__)


class RuleCheck(BaseModel):
    """Result of evaluating a single conditional rule."""

    rule_key: str
    condition_fired: bool
    action_present: bool
    action_injected: bool
    message: str


class RuleViolation(BaseModel):
    """A rule violation that could not be auto-fixed."""

    rule_key: str
    condition_label: str
    expected_action: str
    field: str


class ConsistencyReport(BaseModel):
    """Report produced after checking a draft against deterministic rules."""

    status: str  # passed | warnings | failed
    rules_checked: int
    checks: list[RuleCheck]
    violations: list[RuleViolation]
    injected_actions: list[str]


def _to_decimal(value: Any) -> Decimal | None:
    """Safely convert an intake answer to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _draft_contains_action(content: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    """Check whether any draft section contains one of the action keywords."""
    searchable: list[str] = []
    for field in ("summary", "checklist", "risk_indicators", "missing_information", "recommended_next_steps"):
        value = content.get(field)
        if isinstance(value, str):
            searchable.append(value)
        elif isinstance(value, list):
            searchable.extend(str(item) for item in value)

    text = "\n".join(searchable).lower()
    return any(keyword.lower() in text for keyword in keywords)


def _inject_action(content: dict[str, Any], action: str) -> dict[str, Any]:
    """Inject a mandatory action into the checklist."""
    updated = {k: list(v) if isinstance(v, list) else v for k, v in content.items()}
    checklist = list(updated.get("checklist", []) or [])
    if action not in checklist:
        checklist.append(action)
    updated["checklist"] = checklist
    return updated


def check_draft_consistency(
    content: dict[str, Any],
    answers: dict[str, Any],
    playbook_key: str,
    playbook_version: str | None = None,
) -> tuple[dict[str, Any], ConsistencyReport]:
    """Check a draft against deterministic rules and auto-inject missing actions.

    Returns the (possibly modified) content and a consistency report.
    """
    rules = get_rules_for_playbook(playbook_key, playbook_version)
    checks: list[RuleCheck] = []
    violations: list[RuleViolation] = []
    injected: list[str] = []
    updated_content = content

    for rule in rules:
        value = answers.get(rule.intake_field)
        numeric_value = _to_decimal(value)
        condition_fired = False
        action_present = False
        action_injected = False
        message = f"Rule '{rule.key}': condition not met."

        if numeric_value is not None:
            try:
                condition_fired = evaluate_operator(numeric_value, rule.operator, rule.threshold)
            except ValueError:
                condition_fired = False

        if condition_fired:
            action_present = _draft_contains_action(updated_content, rule.action_keywords)
            if not action_present:
                updated_content = _inject_action(updated_content, rule.action)
                injected.append(rule.action)
                action_injected = True
                action_present = True
            message = (
                f"Rule '{rule.key}': {rule.condition_label} → action "
                f"{'injected' if action_injected else 'present'}."
            )

        checks.append(
            RuleCheck(
                rule_key=rule.key,
                condition_fired=condition_fired,
                action_present=action_present,
                action_injected=action_injected,
                message=message,
            )
        )

        if condition_fired and not action_present and not action_injected:
            # Should not happen because we inject, but keep for safety.
            violations.append(
                RuleViolation(
                    rule_key=rule.key,
                    condition_label=rule.condition_label,
                    expected_action=rule.action,
                    field=rule.intake_field,
                )
            )

    status = "passed"
    if violations:
        status = "failed"
    elif injected:
        status = "warnings"

    report = ConsistencyReport(
        status=status,
        rules_checked=len(rules),
        checks=checks,
        violations=violations,
        injected_actions=injected,
    )
    return updated_content, report
