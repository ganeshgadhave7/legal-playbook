"""API schemas for source-document upload and metadata."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceDocumentUploadMetadata(BaseModel):
    """Required metadata submitted with a DOCX upload."""

    title: str = Field(min_length=1, max_length=300)
    department: str = Field(min_length=1, max_length=120)
    document_type: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=50)
    document_code: str | None = Field(default=None, max_length=120)
    fictional: bool = True


class SourceDocumentResponse(BaseModel):
    """Public source metadata; deliberately excludes storage key and secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    department: str
    document_type: str
    document_code: str | None
    version: str
    status: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    fictional: bool
    created_at: datetime


class SourceDocumentListResponse(BaseModel):
    """Paginated source-document listing."""

    items: list[SourceDocumentResponse]
    limit: int
    offset: int
    total: int


class SourceDocumentDecisionRequest(BaseModel):
    """Approver's decision for a pending source document."""

    decision: str = Field(pattern="^(approved|rejected|changes_requested)$")
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)
