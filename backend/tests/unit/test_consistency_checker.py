"""Unit tests for the consistency checker / deterministic rule engine."""
from app.services.consistency_checker import check_draft_consistency


def test_rule_fires_and_injects_missing_action():
    content = {
        "summary": "Vendor engagement.",
        "checklist": ["Confirm vendor identity."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    answers = {"annual_spend_usd": 50000}

    updated, report = check_draft_consistency(content, answers, "vendor_onboarding", "1")

    assert report.status == "warnings"
    assert len(report.injected_actions) == 1
    assert "human-in-the-loop" in report.injected_actions[0].lower() or "human review" in report.injected_actions[0].lower()
    assert any("human" in item.lower() for item in updated["checklist"])


def test_rule_passes_when_action_present():
    content = {
        "summary": "Vendor engagement.",
        "checklist": ["Require human review because spend exceeds threshold."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    answers = {"annual_spend_usd": 50000}

    updated, report = check_draft_consistency(content, answers, "vendor_onboarding", "1")

    assert report.status == "passed"
    assert len(report.injected_actions) == 0
    assert updated["checklist"] == content["checklist"]


def test_rule_does_not_fire_when_condition_not_met():
    content = {
        "summary": "Vendor engagement.",
        "checklist": ["Confirm vendor identity."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    answers = {"annual_spend_usd": 100}

    updated, report = check_draft_consistency(content, answers, "vendor_onboarding", "1")

    assert report.status == "passed"
    assert len(report.checks) == 1
    assert report.checks[0].condition_fired is False
    assert updated["checklist"] == content["checklist"]


def test_unknown_playbook_has_no_rules():
    content = {
        "summary": "Draft.",
        "checklist": ["Action."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    answers = {"annual_spend_usd": 999999}

    updated, report = check_draft_consistency(content, answers, "nonexistent_playbook")

    assert report.status == "passed"
    assert report.rules_checked == 0
    assert updated == content
