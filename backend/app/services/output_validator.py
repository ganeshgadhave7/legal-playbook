"""Output validator: final gate before a draft is persisted or returned."""
from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.citation_verifier import CitationVerificationReport
from app.services.consistency_checker import ConsistencyReport


class ValidationCheck(BaseModel):
    """A single validation check result."""

    name: str
    passed: bool
    detail: str | None = None


class ValidationResult(BaseModel):
    """Result of the final output validation gate."""

    status: str  # accepted | rejected
    reason: str | None
    checks: list[ValidationCheck]


class DraftValidationError(RuntimeError):
    """Raised when a draft fails the output validation gate."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        super().__init__(result.reason or "Draft failed output validation")


def build_fallback_draft(reason: str) -> dict[str, Any]:
    """Return a safe fallback draft when validation rejects the generated output."""
    return {
        "summary": "Draft generation completed but could not be fully verified against approved sources.",
        "checklist": ["Review intake answers and the approved source library."],
        "risk_indicators": ["Unverified AI output; qualified human review is required."],
        "missing_information": [f"Verification failed: {reason}"],
        "recommended_next_steps": [
            "Retry draft generation after adding or approving relevant source documents.",
            "Contact an editor or admin if the issue persists.",
        ],
    }


def _normalize_report(
    report: CitationVerificationReport | dict[str, Any] | None,
    model: type,
) -> CitationVerificationReport | None:
    if report is None:
        return None
    if isinstance(report, model):
        return report
    return model(**report)


def validate_draft_output(
    content: dict[str, Any],
    verification_report: CitationVerificationReport | dict[str, Any],
    consistency_report: ConsistencyReport | dict[str, Any],
) -> ValidationResult:
    """Validate a draft against citation, consistency, and structural checks."""
    verification_report = _normalize_report(verification_report, CitationVerificationReport)
    consistency_report = _normalize_report(consistency_report, ConsistencyReport)

    if verification_report is None or consistency_report is None:
        return ValidationResult(
            status="rejected",
            reason="Guardrail reports missing",
            checks=[ValidationCheck(name="reports_available", passed=False, detail="missing reports")],
        )

    settings = get_settings()
    checks: list[ValidationCheck] = []

    # 1. Required schema keys
    required_keys = {"summary", "checklist", "risk_indicators", "missing_information", "recommended_next_steps"}
    missing_keys = required_keys - set(content.keys())
    schema_ok = not missing_keys
    checks.append(
        ValidationCheck(
            name="schema",
            passed=schema_ok,
            detail=None if schema_ok else f"Missing keys: {sorted(missing_keys)}",
        )
    )

    # 2. Citation strictness
    citation_ok = verification_report.unsupported_claims == 0
    if settings.strict_citation_mode:
        checks.append(
            ValidationCheck(
                name="citations_strict",
                passed=citation_ok,
                detail=None if citation_ok else f"{verification_report.unsupported_claims} unsupported claims",
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name="citations",
                passed=verification_report.status != "failed",
                detail=f"{verification_report.unsupported_claims} unsupported claims moved to Missing Information",
            )
        )

    # 3. Consistency / rule engine
    consistency_ok = consistency_report.status != "failed"
    checks.append(
        ValidationCheck(
            name="consistency",
            passed=consistency_ok,
            detail=None if consistency_ok else f"{len(consistency_report.violations)} unresolved rule violations",
        )
    )

    # 4. Embedding service did not fail entirely
    embedding_ok = verification_report.status != "failed" or verification_report.supported_claims > 0
    checks.append(
        ValidationCheck(
            name="embedding_service",
            passed=embedding_ok,
            detail=None if embedding_ok else "Embedding service failed during citation verification",
        )
    )

    failed_checks = [c for c in checks if not c.passed]
    if failed_checks:
        reason = "; ".join(
            f"{c.name}: {c.detail or 'failed'}" for c in failed_checks
        )
        return ValidationResult(status="rejected", reason=reason, checks=checks)

    return ValidationResult(status="accepted", reason=None, checks=checks)
