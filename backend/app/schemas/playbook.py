"""Schemas for the initial Vendor Onboarding Playbook intake and history."""
import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VendorOnboardingRequest(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=250)
    service_description: str = Field(min_length=10, max_length=3000)
    annual_spend_usd: float = Field(gt=0, le=1_000_000_000)
    handles_personal_data: bool
    requires_system_access: bool
    uses_subcontractors: bool
    business_criticality: str = Field(pattern="^(low|medium|high|critical)$")


class PlaybookSource(BaseModel):
    document_id: str
    title: str
    document_code: str | None
    version: str
    section: str | None
    page_number: int | None
    chunk_id: str
    similarity: float


class VendorOnboardingCaseResponse(BaseModel):
    case_id: str
    draft_id: str
    case_status: str
    draft_status: str
    created_at: datetime | None = None
    review_feedback: str | None = None
    disclaimer: str
    vendor_summary: str
    checklist: list[str]
    risk_indicators: list[str]
    missing_information: list[str]
    recommended_next_steps: list[str]
    sources: list[PlaybookSource]


class VendorOnboardingCaseListItem(BaseModel):
    case_id: str
    draft_id: str
    vendor_name: str
    playbook_key: str
    playbook_version: str
    case_status: str
    draft_status: str
    created_at: datetime


class VendorOnboardingCaseListResponse(BaseModel):
    items: list[VendorOnboardingCaseListItem]
    total: int


class DraftReviewRequest(BaseModel):
    decision: str = Field(pattern="^(approved|changes_requested|rejected)$")
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)


class DraftReviewResponse(BaseModel):
    case_id: str
    draft_id: str
    case_status: str
    draft_status: str
    decision: str
    reviewer: str
    reason: str | None
    reviewed_at: datetime


class DraftRevisionRequest(BaseModel):
    intake: VendorOnboardingRequest
    revision_note: str = Field(min_length=3, max_length=2000)


class VendorOnboardingDraftResponse(BaseModel):
    disclaimer: str
    vendor_summary: str
    checklist: list[str]
    risk_indicators: list[str]
    missing_information: list[str]
    recommended_next_steps: list[str]
    sources: list[PlaybookSource]


# ---------------------------------------------------------------------------
# Generic playbook schemas
# ---------------------------------------------------------------------------

class IntakeQuestionValidation(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None


class IntakeQuestion(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=250)
    type: str = Field(pattern="^(text|number|boolean|select)$")
    required: bool = True
    options: list[str] | None = None
    validation: IntakeQuestionValidation | None = None

    @field_validator("key", "label")
    @classmethod
    def _strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("intake question key must contain only lowercase letters, digits, and underscores")
        return v


class PlaybookCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_]+$")
    version: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=250)
    department: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    intake_questions: list[IntakeQuestion] = Field(min_length=1)
    prompt_template: str = Field(min_length=10, max_length=20000)


class PlaybookUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    intake_questions: list[IntakeQuestion] | None = None
    prompt_template: str | None = Field(default=None, min_length=10, max_length=20000)
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")


class PlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    version: str
    title: str
    department: str
    description: str | None
    status: str
    intake_questions: list[IntakeQuestion]
    prompt_template: str
    created_at: datetime
    updated_at: datetime


class PlaybookListResponse(BaseModel):
    items: list[PlaybookResponse]
    total: int


class GenericDraftRequest(BaseModel):
    playbook_key: str
    playbook_version: str
    answers: dict[str, str | int | float | bool | None]


class GenericDraftResponse(BaseModel):
    case_id: str
    draft_id: str
    case_status: str
    draft_status: str
    playbook_key: str
    playbook_version: str
    created_at: datetime | None = None
    disclaimer: str
    summary: str
    checklist: list[str]
    risk_indicators: list[str]
    missing_information: list[str]
    recommended_next_steps: list[str]
    sources: list[PlaybookSource]
