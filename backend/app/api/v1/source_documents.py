"""Source-document upload endpoints."""
import hashlib
import io
import logging
from pathlib import Path
from uuid import UUID, uuid4

from docx import Document
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.source_document import (
    SourceDocumentDecisionRequest,
    SourceDocumentListResponse,
    SourceDocumentResponse,
    SourceDocumentUploadMetadata,
)
from app.services.chunking import chunk_blocks
from app.services.docx_extractor import extract_docx_bytes
from app.services.auth import require_user
from app.services.local_file_storage import LocalFileStorage
from app.services.usage_budget import (
    UsageBudgetExceeded,
    read_usage,
    reconcile_usage,
    release_reservation,
    reserve_usage,
)
from app.services.voyage_embeddings import EmbeddingError, VoyageEmbedder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/source-documents", tags=["source-documents"])
settings = get_settings()
storage = LocalFileStorage()

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _validate_docx_container(content: bytes) -> None:
    """Reject non-ZIP files and malformed DOCX containers before saving."""
    if not content.startswith(DOCX_ZIP_SIGNATURES):
        raise HTTPException(status_code=415, detail="Uploaded file is not a valid DOCX container")
    try:
        Document(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=415, detail="DOCX file could not be parsed") from exc


@router.get("", response_model=SourceDocumentListResponse)
async def list_source_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    department: str | None = Query(default=None, min_length=1, max_length=120),
    db: AsyncSession = Depends(get_db_session),
) -> SourceDocumentListResponse:
    """List uploaded document metadata; never returns private storage keys or text."""
    allowed_statuses = {
        "uploaded", "processing", "pending_review", "approved", "indexing",
        "ready", "rejected", "archived", "failed",
    }
    if status_filter is not None and status_filter not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported source document status")

    conditions: list[str] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if status_filter is not None:
        conditions.append("status = :status")
        params["status"] = status_filter
    if department is not None:
        conditions.append("department = :department")
        params["department"] = department.strip()
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_result = await db.execute(
        text(f"SELECT count(*) FROM source_documents {where_clause}"), params
    )
    total = count_result.scalar_one()
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, title, department, document_type, document_code, version,
                   status, original_filename, mime_type, file_size_bytes, sha256,
                   fictional, created_at
            FROM source_documents
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    items = [SourceDocumentResponse(**dict(row)) for row in rows_result.mappings()]
    return SourceDocumentListResponse(items=items, limit=limit, offset=offset, total=total)


async def _set_document_status(db: AsyncSession, document_id: UUID, status_value: str) -> None:
    """Persist a recoverable document status after a failed indexing attempt."""
    try:
        await db.execute(
            text("UPDATE source_documents SET status=:status, updated_at=now() WHERE id=:id"),
            {"id": document_id, "status": status_value},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to restore document status for %s", document_id)


@router.post("/{document_id}/decision", response_model=SourceDocumentResponse)
async def decide_source_document(
    document_id: UUID,
    request: SourceDocumentDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SourceDocumentResponse:
    """Record an approver decision; approved documents become eligible for indexing."""
    row_result = await db.execute(
        text("SELECT status, storage_key FROM source_documents WHERE id = :id FOR UPDATE"),
        {"id": document_id},
    )
    current = row_result.mappings().first()
    if current is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    # Upload starts in `uploaded`; this MVP's explicit approval endpoint also
    # accepts that state. `pending_review` remains supported for future workflow UI.
    if current["status"] == "indexing":
        raise HTTPException(status_code=409, detail="Document indexing is already in progress")
    if current["status"] not in {"uploaded", "pending_review", "approved"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot review a source document in status '{current['status']}'",
        )

    # An already-approved document means indexing previously failed; permit retry
    # without appending another approval decision.
    is_retry = current["status"] == "approved" and request.decision == "approved"
    if current["status"] == "approved" and not is_retry:
        raise HTTPException(status_code=409, detail="Approved document can only retry indexing")

    next_status = {
        "approved": "indexing",
        "rejected": "rejected",
        "changes_requested": "pending_review",
    }[request.decision]

    try:
        if not is_retry:
            await db.execute(
                text(
                    """
                    INSERT INTO approval_decisions (id, source_document_id, decision, reviewer, reason)
                    VALUES (:decision_id, :document_id, :decision, :reviewer, :reason)
                    """
                ),
                {
                    "decision_id": uuid4(),
                    "document_id": document_id,
                    "decision": request.decision,
                    "reviewer": request.reviewer.strip(),
                    "reason": request.reason.strip() if request.reason else None,
                },
            )
        result = await db.execute(
            text(
                """
                UPDATE source_documents
                SET status = :status, updated_at = now()
                WHERE id = :id
                RETURNING id, title, department, document_type, document_code,
                    version, status, original_filename, mime_type, file_size_bytes,
                    sha256, fictional, created_at
                """
            ),
            {"id": document_id, "status": next_status},
        )
        updated = result.mappings().one()
        if request.decision != "approved":
            await db.commit()
            return SourceDocumentResponse(**dict(updated))

        # Commit the decision and indexing state first. This makes failures visible
        # and allows an explicit retry without recording duplicate approvals.
        await db.commit()
        await db.execute(
            text("UPDATE source_documents SET status='indexing', updated_at=now() WHERE id=:id"),
            {"id": document_id},
        )
        await db.commit()
        # Re-approval retries indexing; replace previous partial chunks only after
        # the new embeddings are ready, in the same transaction as the new chunks.
        blocks = extract_docx_bytes(storage.path_for(current["storage_key"]).read_bytes())
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise HTTPException(status_code=422, detail="No text chunks were produced")

        embedder = VoyageEmbedder()
        # Reserve a conservative estimate before sending any content to the provider.
        estimated_tokens = sum(max(1, len(chunk.content) // 3) for chunk in chunks)
        await reserve_usage(db, estimated_tokens)
        try:
            vectors, actual_tokens = embedder.embed_documents([chunk.content for chunk in chunks])
            await reconcile_usage(db, estimated_tokens, actual_tokens)
        except Exception:
            await release_reservation(db, estimated_tokens)
            raise

        insert_chunks = text(
                """
                INSERT INTO document_chunks (
                    id, source_document_id, chunk_index, content, section,
                    page_number, embedding
                ) VALUES (
                    :id, :source_document_id, :chunk_index, :content, :section,
                    :page_number, :embedding
                )
                """
            ).bindparams(bindparam("embedding", type_=Vector(settings.voyage_embedding_dimensions)))
        await db.execute(
            text("DELETE FROM document_chunks WHERE source_document_id=:id"),
            {"id": document_id},
        )
        await db.execute(
            insert_chunks,
            [
                {
                    "id": uuid4(),
                    "source_document_id": document_id,
                    "chunk_index": chunk.index,
                    "content": chunk.content,
                    "section": chunk.section,
                    "page_number": chunk.page_number,
                    "embedding": vector,
                }
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )
        await db.execute(
            text("UPDATE source_documents SET status='ready', updated_at=now() WHERE id=:id"),
            {"id": document_id},
        )
        updated = {**dict(updated), "status": "ready"}
        await db.commit()
    except HTTPException:
        await db.rollback()
        if request.decision == "approved":
            await _set_document_status(db, document_id, "approved")
        raise
    except UsageBudgetExceeded as exc:
        await db.rollback()
        await _set_document_status(db, document_id, "approved")
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmbeddingError as exc:
        await db.rollback()
        await _set_document_status(db, document_id, "approved")
        logger.warning("Embedding failed for source document %s", document_id)
        raise HTTPException(status_code=502, detail="Could not embed source document; it remains approved and can be retried") from exc
    except Exception as exc:
        await db.rollback()
        if request.decision == "approved":
            await _set_document_status(db, document_id, "approved")
        logger.exception("Failed to record source-document review")
        raise HTTPException(status_code=500, detail="Could not complete source indexing") from exc

    return SourceDocumentResponse(**dict(updated))


@router.post("", response_model=SourceDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_source_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form(...),
    document_type: str = Form(...),
    version: str = Form(...),
    document_code: str | None = Form(default=None),
    fictional: bool = Form(default=True),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user),
) -> SourceDocumentResponse:
    """Validate, extract, store, and register a DOCX in `uploaded` state."""
    original_filename = Path(file.filename or "upload.docx").name
    if Path(original_filename).suffix.lower() != ".docx":
        raise HTTPException(status_code=415, detail="Only .docx files are supported")

    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds the configured limit")
    _validate_docx_container(content)

    try:
        blocks = extract_docx_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        metadata = SourceDocumentUploadMetadata(
            title=title.strip(),
            department=department.strip(),
            document_type=document_type.strip(),
            version=version.strip(),
            document_code=document_code.strip() if document_code else None,
            fictional=fictional,
        )
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        raise
    sha256 = hashlib.sha256(content).hexdigest()
    storage_key, stored_path = storage.save_docx(content, original_filename)

    try:
        result = await db.execute(
            text(
                """
                INSERT INTO source_documents (
                    id, title, department, document_type, document_code, version,
                    status, storage_key, original_filename, mime_type,
                    file_size_bytes, sha256, fictional
                ) VALUES (
                    :id, :title, :department, :document_type, :document_code, :version,
                    'uploaded', :storage_key, :original_filename, :mime_type,
                    :file_size_bytes, :sha256, :fictional
                ) RETURNING id, title, department, document_type, document_code,
                    version, status, original_filename, mime_type, file_size_bytes,
                    sha256, fictional, created_at
                """
            ),
            {
                "id": uuid4(),
                "title": metadata.title,
                "department": metadata.department,
                "document_type": metadata.document_type,
                "document_code": metadata.document_code,
                "version": metadata.version,
                "storage_key": storage_key,
                "original_filename": original_filename,
                "mime_type": DOCX_MIME,
                "file_size_bytes": len(content),
                "sha256": sha256,
                "fictional": metadata.fictional,
            },
        )
        row = result.mappings().one()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        storage.delete(storage_key)
        # Convert expected uniqueness conflicts into a helpful client error.
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            logger.info("Rejected duplicate source document version")
            raise HTTPException(
                status_code=409,
                detail="This document code and version already exist. Choose a new version for another upload.",
            ) from exc
        logger.exception("Failed to register uploaded source document")
        raise HTTPException(status_code=500, detail="Could not register uploaded document") from exc
    finally:
        await file.close()

    # Log only safe metadata; do not log document content or secrets.
    logger.info("Uploaded source document %s with %d extracted blocks", row["id"], len(blocks))
    return SourceDocumentResponse(**dict(row))
