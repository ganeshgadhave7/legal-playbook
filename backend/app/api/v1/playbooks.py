"""Vendor Onboarding Playbook endpoints."""
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.playbook import (
    GenericDraftRequest,
    GenericDraftResponse,
    PlaybookCreateRequest,
    PlaybookListResponse,
    PlaybookResponse,
    PlaybookUpdateRequest,
    VendorOnboardingCaseListItem,
    VendorOnboardingCaseListResponse,
    DraftReviewRequest,
    DraftReviewResponse,
    DraftRevisionRequest,
    VendorOnboardingCaseResponse,
    VendorOnboardingRequest,
)
from app.services.usage_budget import UsageBudgetExceeded
from app.services.voyage_embeddings import EmbeddingError
from app.workflows.playbook_draft import (
    IntakeValidationError as PlaybookIntakeValidationError,
    PlaybookNotFound,
    run_playbook_draft,
)
from app.workflows.vendor_onboarding import DISCLAIMER, run_vendor_onboarding

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# ---------------------------------------------------------------------------
# Playbook definition CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=PlaybookListResponse)
async def list_playbooks(
    status: str | None = Query(default=None, pattern="^(draft|published|archived)$"),
    department: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> PlaybookListResponse:
    """List playbooks with optional status and department filters."""
    conditions: list[str] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if status is not None:
        conditions.append("status = :status")
        params["status"] = status
    if department is not None:
        conditions.append("department = :department")
        params["department"] = department.strip()
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_result = await db.execute(
        text(f"SELECT count(*) FROM playbooks {where_clause}"), params
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT id, key, version, title, department, description,
                   status, intake_questions, prompt_template,
                   created_at, updated_at
            FROM playbooks
            {where_clause}
            ORDER BY created_at DESC, title ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    items = [PlaybookResponse(**dict(row)) for row in result.mappings()]
    return PlaybookListResponse(items=items, total=total)


@router.post("", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    request: PlaybookCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> PlaybookResponse:
    """Create a new playbook draft."""
    existing = await db.execute(
        text("SELECT id FROM playbooks WHERE key = :key AND version = :version"),
        {"key": request.key, "version": request.version},
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Playbook '{request.key}' v{request.version} already exists",
        )

    playbook_id = uuid4()
    result = await db.execute(
        text(
            """
            INSERT INTO playbooks (
                id, key, version, title, department, description,
                status, intake_questions, prompt_template, created_at, updated_at
            ) VALUES (
                :id, :key, :version, :title, :department, :description,
                'draft', CAST(:intake_questions AS jsonb), :prompt_template,
                now(), now()
            )
            RETURNING id, key, version, title, department, description,
                      status, intake_questions, prompt_template, created_at, updated_at
            """
        ),
        {
            "id": playbook_id,
            "key": request.key,
            "version": request.version,
            "title": request.title,
            "department": request.department,
            "description": request.description,
            "intake_questions": json.dumps([q.model_dump() for q in request.intake_questions]),
            "prompt_template": request.prompt_template,
        },
    )
    await db.commit()
    return PlaybookResponse(**dict(result.mappings().one()))


async def _get_latest_playbook_row(key: str, db: AsyncSession) -> dict | None:
    """Return the latest version of a playbook by key."""
    result = await db.execute(
        text(
            """
            SELECT id, key, version, title, department, description,
                   status, intake_questions, prompt_template, created_at, updated_at
            FROM playbooks
            WHERE key = :key
            ORDER BY created_at DESC, version DESC
            LIMIT 1
            """
        ),
        {"key": key},
    )
    row = result.mappings().first()
    return dict(row) if row else None


@router.get("/{key}", response_model=PlaybookResponse)
async def get_playbook(
    key: str,
    db: AsyncSession = Depends(get_db_session),
) -> PlaybookResponse:
    """Get the latest version of a playbook by key."""
    row = await _get_latest_playbook_row(key, db)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Playbook '{key}' not found")
    return PlaybookResponse(**row)


@router.put("/{key}", response_model=PlaybookResponse)
async def update_playbook(
    key: str,
    request: PlaybookUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> PlaybookResponse:
    """Update the latest draft version of a playbook."""
    row = await _get_latest_playbook_row(key, db)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Playbook '{key}' not found")
    if row["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Only draft playbooks can be edited; current status is '{row['status']}'",
        )

    updates: dict[str, object] = {}
    if request.title is not None:
        updates["title"] = request.title
    if request.department is not None:
        updates["department"] = request.department
    if request.description is not None:
        updates["description"] = request.description
    if request.intake_questions is not None:
        updates["intake_questions"] = json.dumps([q.model_dump() for q in request.intake_questions])
    if request.prompt_template is not None:
        updates["prompt_template"] = request.prompt_template
    if request.status is not None:
        updates["status"] = request.status

    if not updates:
        return PlaybookResponse(**row)

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = row["id"]
    result = await db.execute(
        text(
            f"""
            UPDATE playbooks
            SET {set_clause}, updated_at = now()
            WHERE id = :id
            RETURNING id, key, version, title, department, description,
                      status, intake_questions, prompt_template, created_at, updated_at
            """
        ),
        updates,
    )
    await db.commit()
    return PlaybookResponse(**dict(result.mappings().one()))


@router.post("/{key}/publish", response_model=PlaybookResponse)
async def publish_playbook(
    key: str,
    db: AsyncSession = Depends(get_db_session),
) -> PlaybookResponse:
    """Publish the latest draft version of a playbook."""
    row = await _get_latest_playbook_row(key, db)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Playbook '{key}' not found")
    if row["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Only draft playbooks can be published; current status is '{row['status']}'",
        )

    result = await db.execute(
        text(
            """
            UPDATE playbooks
            SET status = 'published', updated_at = now()
            WHERE id = :id
            RETURNING id, key, version, title, department, description,
                      status, intake_questions, prompt_template, created_at, updated_at
            """
        ),
        {"id": row["id"]},
    )
    await db.commit()
    return PlaybookResponse(**dict(result.mappings().one()))


# ---------------------------------------------------------------------------
# Vendor Onboarding Playbook endpoints (legacy wrapper around generic engine)
# ---------------------------------------------------------------------------

@router.get("/vendor-onboarding/cases", response_model=VendorOnboardingCaseListResponse)
async def list_vendor_onboarding_cases(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> VendorOnboardingCaseListResponse:
    count_result = await db.execute(text("SELECT count(*) FROM cases WHERE playbook_key='vendor_onboarding'"))
    total = count_result.scalar_one()
    result = await db.execute(
        text(
            """
            SELECT c.id::text AS case_id, d.id::text AS draft_id,
                   c.intake_answers->>'vendor_name' AS vendor_name,
                   c.playbook_key, c.playbook_version, c.status AS case_status,
                   d.status AS draft_status, c.created_at
            FROM cases c
            JOIN drafts d ON d.case_id = c.id
            WHERE c.playbook_key = 'vendor_onboarding'
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit, "offset": offset},
    )
    items = [VendorOnboardingCaseListItem(**dict(row)) for row in result.mappings()]
    return VendorOnboardingCaseListResponse(items=items, total=total)


@router.get("/vendor-onboarding/cases/{case_id}", response_model=VendorOnboardingCaseResponse)
async def get_vendor_onboarding_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> VendorOnboardingCaseResponse:
    result = await db.execute(
        text(
            """
            SELECT c.id::text AS case_id, d.id::text AS draft_id,
                   c.status AS case_status, d.status AS draft_status,
                   c.created_at, d.content,
                   (SELECT reason FROM draft_reviews WHERE draft_id=d.id AND decision='changes_requested' ORDER BY created_at DESC LIMIT 1) AS review_feedback
            FROM cases c
            JOIN drafts d ON d.case_id = c.id
            WHERE c.id = :case_id AND c.playbook_key='vendor_onboarding'
            ORDER BY d.version DESC
            LIMIT 1
            """
        ),
        {"case_id": case_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor onboarding case not found")

    citations_result = await db.execute(
        text(
            """
            SELECT dc.chunk_id::text AS chunk_id, dc.similarity,
                   sd.id::text AS document_id, sd.title, sd.document_code, sd.version,
                   ch.section, ch.page_number
            FROM draft_citations dc
            JOIN drafts d ON d.id=dc.draft_id
            JOIN document_chunks ch ON ch.id=dc.chunk_id
            JOIN source_documents sd ON sd.id=ch.source_document_id
            WHERE d.id=:draft_id
            ORDER BY dc.rank
            """
        ),
        {"draft_id": row["draft_id"]},
    )
    from app.schemas.playbook import PlaybookSource

    sources = [PlaybookSource(**dict(citation)) for citation in citations_result.mappings()]
    return VendorOnboardingCaseResponse(
        case_id=str(row["case_id"]),
        draft_id=str(row["draft_id"]),
        case_status=row["case_status"],
        draft_status=row["draft_status"],
        created_at=row["created_at"],
        review_feedback=row["review_feedback"],
        disclaimer=DISCLAIMER,
        vendor_summary=row["content"].get("vendor_summary", ""),
        checklist=row["content"].get("checklist", []),
        risk_indicators=row["content"].get("risk_indicators", []),
        missing_information=row["content"].get("missing_information", []),
        recommended_next_steps=row["content"].get("recommended_next_steps", []),
        sources=sources,
    )


@router.post("/vendor-onboarding/cases/{case_id}/revisions", response_model=VendorOnboardingCaseResponse)
async def revise_vendor_onboarding_draft(
    case_id: UUID,
    request: DraftRevisionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> VendorOnboardingCaseResponse:
    """Create a new draft version after an approver requested changes."""
    case_result = await db.execute(
        text("SELECT id,status FROM cases WHERE id=:id AND playbook_key='vendor_onboarding' FOR UPDATE"),
        {"id": case_id},
    )
    case = case_result.mappings().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Vendor onboarding case not found")
    if case["status"] != "changes_requested":
        raise HTTPException(status_code=409, detail="This case does not have requested changes")

    latest = await db.execute(
        text("SELECT id,version FROM drafts WHERE case_id=:id ORDER BY version DESC LIMIT 1 FOR UPDATE"),
        {"id": case_id},
    )
    latest_draft = latest.mappings().first()
    if latest_draft is None or latest_draft["id"] is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    try:
        new_draft = await run_vendor_onboarding(
            request.intake,
            db,
            existing_case_id=case_id,
            revision_number=int(latest_draft["version"]) + 1,
        )
        await db.execute(
            text("INSERT INTO draft_reviews (id,draft_id,reviewer,decision,reason) VALUES (:id,:draft_id,:reviewer,'changes_requested',:reason)"),
            {"id": uuid4(), "draft_id": latest_draft["id"], "reviewer": "requester-resubmission", "reason": request.revision_note.strip()},
        )
        await db.commit()
        return new_draft
    except UsageBudgetExceeded as exc:
        await db.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmbeddingError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Could not embed revised intake") from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not create revised draft") from exc


@router.post("/vendor-onboarding/cases/{case_id}/review", response_model=DraftReviewResponse)
async def review_vendor_onboarding_draft(
    case_id: UUID,
    request: DraftReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> DraftReviewResponse:
    """Approve, request changes to, or reject the latest pending case draft."""
    result = await db.execute(
        text(
            """
            SELECT c.id AS case_id, c.status AS case_status, d.id AS draft_id,
                   d.status AS draft_status
            FROM cases c
            JOIN drafts d ON d.case_id=c.id
            WHERE c.id=:case_id AND c.playbook_key='vendor_onboarding'
            ORDER BY d.version DESC
            LIMIT 1
            FOR UPDATE OF c, d
            """
        ),
        {"case_id": case_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor onboarding draft not found")
    if row["draft_status"] not in {"pending_review", "changes_requested"}:
        raise HTTPException(status_code=409, detail=f"Draft cannot be reviewed in status '{row['draft_status']}'")

    new_draft_status = {
        "approved": "approved",
        "changes_requested": "changes_requested",
        "rejected": "rejected",
    }[request.decision]
    new_case_status = {
        "approved": "approved",
        "changes_requested": "changes_requested",
        "rejected": "rejected",
    }[request.decision]
    reviewed_at = datetime.now(timezone.utc)
    try:
        await db.execute(
            text(
                """
                INSERT INTO draft_reviews (id,draft_id,reviewer,decision,reason,created_at)
                VALUES (:id,:draft_id,:reviewer,:decision,:reason,:created_at)
                """
            ),
            {
                "id": uuid4(),
                "draft_id": row["draft_id"],
                "reviewer": request.reviewer.strip(),
                "decision": request.decision,
                "reason": request.reason.strip() if request.reason else None,
                "created_at": reviewed_at,
            },
        )
        await db.execute(text("UPDATE drafts SET status=:status WHERE id=:id"), {"status": new_draft_status, "id": row["draft_id"]})
        await db.execute(text("UPDATE cases SET status=:status WHERE id=:id"), {"status": new_case_status, "id": row["case_id"]})
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not save draft review decision") from exc

    return DraftReviewResponse(
        case_id=str(row["case_id"]),
        draft_id=str(row["draft_id"]),
        case_status=new_case_status,
        draft_status=new_draft_status,
        decision=request.decision,
        reviewer=request.reviewer.strip(),
        reason=request.reason.strip() if request.reason else None,
        reviewed_at=reviewed_at,
    )


@router.post("/vendor-onboarding/draft", response_model=VendorOnboardingCaseResponse)
async def draft_vendor_onboarding(
    request: VendorOnboardingRequest,
    db: AsyncSession = Depends(get_db_session),
) -> VendorOnboardingCaseResponse:
    """Run the generic playbook workflow for the legacy vendor onboarding playbook."""
    try:
        generic = await run_playbook_draft("vendor_onboarding", "1", request.model_dump(), db)
        return VendorOnboardingCaseResponse(
            case_id=generic.case_id,
            draft_id=generic.draft_id,
            case_status=generic.case_status,
            draft_status=generic.draft_status,
            created_at=generic.created_at,
            disclaimer=generic.disclaimer,
            vendor_summary=generic.summary,
            checklist=generic.checklist,
            risk_indicators=generic.risk_indicators,
            missing_information=generic.missing_information,
            recommended_next_steps=generic.recommended_next_steps,
            sources=generic.sources,
        )
    except PlaybookNotFound as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaybookIntakeValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UsageBudgetExceeded as exc:
        await db.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmbeddingError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Could not embed playbook intake") from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not prepare vendor onboarding draft") from exc


@router.post("/draft", response_model=GenericDraftResponse)
async def draft_generic_playbook(
    request: GenericDraftRequest,
    db: AsyncSession = Depends(get_db_session),
) -> GenericDraftResponse:
    """Run the generic playbook workflow for any published playbook."""
    try:
        return await run_playbook_draft(
            request.playbook_key,
            request.playbook_version,
            request.answers,
            db,
        )
    except PlaybookNotFound as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaybookIntakeValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UsageBudgetExceeded as exc:
        await db.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmbeddingError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Could not embed playbook intake") from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not prepare playbook draft") from exc
