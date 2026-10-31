"""Unit tests for the output validator / final gate."""
import pytest

from app.services.citation_verifier import CitationVerificationReport, ClaimScore
from app.services.consistency_checker import ConsistencyReport
from app.services.output_validator import (
    ValidationResult,
    build_fallback_draft,
    validate_draft_output,
)


def _make_verification(status: str, unsupported: int = 0) -> CitationVerificationReport:
    return CitationVerificationReport(
        status=status,
        threshold=0.72,
        supported_claims=1,
        unsupported_claims=unsupported,
        low_confidence_claims=0,
        claims=[ClaimScore(claim="Claim", best_similarity=0.91, supported=unsupported == 0)],
        unsupported_details=[],
    )


def _make_consistency(status: str, violations: int = 0) -> ConsistencyReport:
    return ConsistencyReport(
        status=status,
        rules_checked=1,
        checks=[],
        violations=[],
        injected_actions=[],
    )


def test_valid_draft_is_accepted():
    content = {
        "summary": "Summary.",
        "checklist": ["Action."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    result = validate_draft_output(
        content,
        _make_verification("verified"),
        _make_consistency("passed"),
    )
    assert result.status == "accepted"
    assert result.reason is None


def test_missing_schema_key_is_rejected():
    content = {
        "summary": "Summary.",
        "checklist": ["Action."],
        # missing risk_indicators etc.
    }
    result = validate_draft_output(
        content,
        _make_verification("verified"),
        _make_consistency("passed"),
    )
    assert result.status == "rejected"
    assert "schema" in result.reason.lower()


def test_unsupported_claim_in_strict_mode_is_rejected(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "strict_citation_mode", True)
    content = {
        "summary": "Summary.",
        "checklist": ["Action."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    result = validate_draft_output(
        content,
        _make_verification("verified_with_warnings", unsupported=1),
        _make_consistency("passed"),
    )
    assert result.status == "rejected"
    assert "unsupported" in result.reason.lower()


def test_unsupported_claim_in_lenient_mode_is_accepted():
    content = {
        "summary": "Summary.",
        "checklist": ["Action."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    result = validate_draft_output(
        content,
        _make_verification("verified_with_warnings", unsupported=1),
        _make_consistency("passed"),
    )
    assert result.status == "accepted"


def test_consistency_failure_is_rejected():
    content = {
        "summary": "Summary.",
        "checklist": ["Action."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    result = validate_draft_output(
        content,
        _make_verification("verified"),
        _make_consistency("failed"),
    )
    assert result.status == "rejected"
    assert "consistency" in result.reason.lower()


def test_fallback_draft_has_required_keys():
    fallback = build_fallback_draft("test reason")
    required = {"summary", "checklist", "risk_indicators", "missing_information", "recommended_next_steps"}
    assert required.issubset(set(fallback.keys()))
    assert "test reason" in fallback["missing_information"][0]
