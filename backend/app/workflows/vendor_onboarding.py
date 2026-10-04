"""LangGraph workflow for the fictional Vendor Onboarding playbook draft."""
import json
from typing import NotRequired, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.playbook import (
    PlaybookSource,
    VendorOnboardingCaseResponse,
    VendorOnboardingRequest,
)
from app.services.llm_client import DraftContentOutput, LLMError, generate_vendor_onboarding_draft
from app.services.retrieval_utils import deduplicate_passages
from app.services.usage_budget import (
    UsageBudgetExceeded,
    reconcile_usage,
    release_reservation,
    reserve_usage,
)
from app.services.voyage_embeddings import EmbeddingError, VoyageEmbedder

DISCLAIMER = (
    "Fictional portfolio demonstration only. This is an AI-generated draft, "
    "not legal advice or an approved legal determination; qualified human review is required."
)


class VendorOnboardingState(TypedDict):
    """Data passed through the onboarding workflow nodes."""

    request: VendorOnboardingRequest
    db: AsyncSession
    existing_case_id: NotRequired[UUID]
    revision_number: NotRequired[int]
    query: NotRequired[str]
    case_id: NotRequired[UUID]
    query_vector: NotRequired[list[float]]
    passages: NotRequired[list[dict]]
    vendor_summary: NotRequired[str]
    checklist: NotRequired[list[str]]
    risk_indicators: NotRequired[list[str]]
    missing_information: NotRequired[list[str]]
    recommended_next_steps: NotRequired[list[str]]
    response: NotRequired[VendorOnboardingCaseResponse]
    draft_id: NotRequired[UUID]


def validate_intake(state: VendorOnboardingState) -> dict:
    """Build the retrieval query from already schema-validated user answers."""
    request = state["request"]
    query = (
        "Vendor onboarding requirements for: "
        f"{request.service_description}. Vendor {request.vendor_name}; "
        f"annual spend USD {request.annual_spend_usd:.2f}; "
        f"personal data={request.handles_personal_data}; "
        f"system access={request.requires_system_access}; "
        f"subcontractors={request.uses_subcontractors}; "
        f"business criticality={request.business_criticality}."
    )
    return {"query": query}


async def retrieve_sources(state: VendorOnboardingState) -> dict:
    """Embed the intake and retrieve only ready fictional Procurement sources."""
    settings = get_settings()
    query = state["query"]
    estimate = max(1, len(query) // 3)
    db = state["db"]

    try:
        embedder = VoyageEmbedder()
        await reserve_usage(db, estimate)
    except UsageBudgetExceeded:
        raise
    except EmbeddingError:
        raise

    try:
        vectors, actual_tokens = embedder.embed_documents([query])
    except EmbeddingError:
        # Voyage may have rejected the call before charging; release the reservation.
        await release_reservation(db, estimate)
        await db.commit()
        raise

    # Once the provider returned usage, account for it even if later local DB work fails.
    await reconcile_usage(db, estimate, actual_tokens)
    await db.commit()

    vector = vectors[0]
    if len(vector) != settings.voyage_embedding_dimensions:
        raise EmbeddingError("Query embedding dimension did not match configured dimension")

    statement = text(
        """
        SELECT dc.id AS chunk_id, sd.id AS document_id, sd.title,
               sd.document_code, sd.version, dc.section, dc.page_number,
               dc.content, 1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.source_document_id
        WHERE sd.status = 'ready' AND sd.fictional = true
          AND sd.department = 'Procurement'
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT 8
        """
    ).bindparams(bindparam("embedding", type_=Vector(settings.voyage_embedding_dimensions)))
    result = await db.execute(statement, {"embedding": vector})
    passages = [dict(row) for row in result.mappings()]
    # Remove duplicate content from multiple uploads of the same source.
    passages = deduplicate_passages(passages)
    return {"passages": passages}


async def assess_evidence_and_risks(state: VendorOnboardingState) -> dict:
    """Create checklist and risk flags using an LLM grounded in retrieved policy evidence.

    If the LLM is unavailable, falls back to deterministic safety checks so the
    workflow never produces an empty or silently broken draft.
    """
    request = state["request"]
    passages = state.get("passages", [])

    # Always attempt the LLM first for a richer, source-grounded draft.
    try:
        draft = await generate_vendor_onboarding_draft(
            request.model_dump_json(),
            passages,
        )
    except LLMError:
        draft = DraftContentOutput(
            vendor_summary=(
                f"{request.vendor_name} is proposed to provide: {request.service_description}. "
                f"Estimated annual spend: ${request.annual_spend_usd:,.2f}."
            ),
            checklist=[
                "Confirm the vendor's legal identity and scope of services with the requester.",
                "Record annual spend and route approvals according to approved procurement guidance.",
            ],
            risk_indicators=[],
            missing_information=["LLM generation is unavailable; this draft uses only deterministic checks."],
            recommended_next_steps=["Retry draft generation or review manually."],
        )

    # Enforce mandatory safety items that must never be omitted, regardless of LLM output.
    checklist = list(draft.checklist)
    risks = list(draft.risk_indicators)
    missing = list(draft.missing_information)
    next_steps = list(draft.recommended_next_steps)

    if request.handles_personal_data and not any("personal data" in r.lower() for r in risks):
        risks.append("Vendor will handle personal data; privacy and data-protection review is needed.")
        next_steps.append("Refer the case to the privacy/compliance approver before onboarding.")
    if request.requires_system_access and not any("system access" in r.lower() for r in risks):
        risks.append("Vendor requires system access; access scope and security review are needed.")
        next_steps.append("Specify requested systems, least-privilege scope, and access duration for review.")
    if request.uses_subcontractors and not any("subcontractor" in r.lower() for r in risks):
        risks.append("Vendor uses subcontractors; identify them and review applicable third-party controls.")
        next_steps.append("Collect subcontractor names, roles, and data/access involvement.")
    if request.business_criticality in {"high", "critical"} and not any(
        "critical" in r.lower() or "business owner" in s.lower() for r in risks for s in next_steps
    ):
        risks.append("Service is marked high or critical business importance; human risk review is needed.")
        next_steps.append("Route the case to the designated business owner and risk approver.")

    if not passages and not any("no ready" in m.lower() for m in missing):
        missing.append("No ready, approved fictional Procurement source was retrieved.")
        next_steps.append("Do not treat this output as policy-grounded; ask an approver to review the source library.")
    if not risks:
        risks.append("No risk trigger was identified from the supplied intake answers; human review is still required.")
    if not next_steps:
        next_steps.append("Submit this draft and its citations to the assigned human approver.")

    return {
        "vendor_summary": draft.vendor_summary,
        "checklist": checklist,
        "risk_indicators": risks,
        "missing_information": missing,
        "recommended_next_steps": next_steps,
    }


async def assemble_draft(state: VendorOnboardingState) -> dict:
    """Persist a pending-review draft and its citations, then form the response."""
    db = state["db"]
    case_id = state.get("existing_case_id") or uuid4()
    draft_id = uuid4()
    revision_number = state.get("revision_number", 1)
    sources = [
        PlaybookSource(
            document_id=str(row["document_id"]),
            title=row["title"],
            document_code=row["document_code"],
            version=row["version"],
            section=row["section"],
            page_number=row["page_number"],
            chunk_id=str(row["chunk_id"]),
            similarity=float(row["similarity"]),
        )
        for row in state.get("passages", [])
    ]
    content = {
        "vendor_summary": state["vendor_summary"],
        "checklist": state["checklist"],
        "risk_indicators": state["risk_indicators"],
        "missing_information": state["missing_information"],
        "recommended_next_steps": state["recommended_next_steps"],
    }
    request = state["request"]
    if revision_number == 1:
        case_insert = await db.execute(
            text(
                """
                INSERT INTO cases (id, playbook_key, playbook_version, status, intake_answers)
                VALUES (:id, 'vendor_onboarding', '1', 'draft_pending_review', CAST(:answers AS jsonb))
                RETURNING created_at
                """
            ),
            {"id": case_id, "answers": request.model_dump_json()},
        )
        created_at = case_insert.scalar_one()
    else:
        case_insert = await db.execute(
            text("UPDATE cases SET status='draft_pending_review', intake_answers=CAST(:answers AS jsonb) WHERE id=:id RETURNING created_at"),
            {"id": case_id, "answers": request.model_dump_json()},
        )
        created_at = case_insert.scalar_one()
    await db.execute(
        text(
            """
            INSERT INTO drafts (id, case_id, version, status, content, disclaimer)
            VALUES (:id, :case_id, :version, 'pending_review', CAST(:content AS jsonb), :disclaimer)
            """
        ),
        {"id": draft_id, "case_id": case_id, "version": revision_number, "content": json.dumps(content), "disclaimer": DISCLAIMER},
    )
    if sources:
        await db.execute(
            text(
                """
                INSERT INTO draft_citations (id, draft_id, chunk_id, rank, similarity)
                VALUES (:id, :draft_id, :chunk_id, :rank, :similarity)
                """
            ),
            [
                {
                    "id": uuid4(),
                    "draft_id": draft_id,
                    "chunk_id": UUID(source.chunk_id),
                    "rank": rank,
                    "similarity": source.similarity,
                }
                for rank, source in enumerate(sources, start=1)
            ],
        )
    await db.commit()

    response = VendorOnboardingCaseResponse(
        case_id=str(case_id),
        draft_id=str(draft_id),
        case_status="draft_pending_review",
        draft_status="pending_review",
        created_at=created_at,
        disclaimer=DISCLAIMER,
        vendor_summary=state["vendor_summary"],
        checklist=state["checklist"],
        risk_indicators=state["risk_indicators"],
        missing_information=state["missing_information"],
        recommended_next_steps=state["recommended_next_steps"],
        sources=sources,
    )
    return {"response": response, "case_id": case_id, "draft_id": draft_id}


_builder = StateGraph(VendorOnboardingState)
_builder.add_node("validate_intake", validate_intake)
_builder.add_node("retrieve_sources", retrieve_sources)
_builder.add_node("assess_evidence_and_risks", assess_evidence_and_risks)
_builder.add_node("assemble_draft", assemble_draft)
_builder.add_edge(START, "validate_intake")
_builder.add_edge("validate_intake", "retrieve_sources")
_builder.add_edge("retrieve_sources", "assess_evidence_and_risks")
_builder.add_edge("assess_evidence_and_risks", "assemble_draft")
_builder.add_edge("assemble_draft", END)
vendor_onboarding_graph = _builder.compile()


async def run_vendor_onboarding(
    request: VendorOnboardingRequest,
    db: AsyncSession,
    *,
    existing_case_id: UUID | None = None,
    revision_number: int = 1,
) -> VendorOnboardingCaseResponse:
    """Invoke the compiled graph and return its completed draft."""
    result = await vendor_onboarding_graph.ainvoke(
        {"request": request, "db": db, "existing_case_id": existing_case_id, "revision_number": revision_number}
    )
    return result["response"]
