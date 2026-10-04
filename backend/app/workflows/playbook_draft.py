"""Generic LangGraph workflow for any published playbook."""
import json
from typing import Any, NotRequired, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.playbook import GenericDraftResponse, PlaybookSource
from app.services.llm_client import LLMError, generate_playbook_draft
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


class PlaybookDraftState(TypedDict):
    """Data passed through the generic playbook draft nodes."""

    playbook_key: str
    playbook_version: str
    answers: dict[str, Any]
    db: AsyncSession

    playbook_id: NotRequired[UUID]
    playbook: NotRequired[dict[str, Any]]
    query: NotRequired[str]
    passages: NotRequired[list[dict[str, Any]]]
    draft_content: NotRequired[dict[str, Any]]
    case_id: NotRequired[UUID]
    draft_id: NotRequired[UUID]
    response: NotRequired[GenericDraftResponse]


class PlaybookNotFound(RuntimeError):
    """Raised when the requested playbook does not exist or is not published."""


class IntakeValidationError(RuntimeError):
    """Raised when intake answers fail validation against the playbook schema."""


async def load_playbook(state: PlaybookDraftState) -> dict:
    """Load and verify the playbook from the database."""
    db = state["db"]
    result = await db.execute(
        text(
            """
            SELECT id, key, version, title, department, description,
                   status, intake_questions, prompt_template
            FROM playbooks
            WHERE key = :key AND version = :version
            """
        ),
        {"key": state["playbook_key"], "version": state["playbook_version"]},
    )
    row = result.mappings().first()
    if row is None:
        raise PlaybookNotFound(f"Playbook '{state['playbook_key']}' v{state['playbook_version']} not found")
    if row["status"] != "published":
        raise PlaybookNotFound(f"Playbook '{state['playbook_key']}' is not published")
    return {"playbook_id": row["id"], "playbook": dict(row)}


def _validate_answers(playbook: dict[str, Any], answers: dict[str, Any]) -> None:
    """Validate intake answers against the playbook's question schema."""
    questions = playbook.get("intake_questions", [])
    errors: list[str] = []

    for question in questions:
        key = question["key"]
        value = answers.get(key)
        required = question.get("required", False)
        qtype = question["type"]
        validation = question.get("validation") or {}

        if required and (value is None or value == ""):
            errors.append(f"'{key}' is required")
            continue

        if value is None:
            continue

        if qtype == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")
                continue
            if validation.get("gt") is not None and value <= validation["gt"]:
                errors.append(f"'{key}' must be greater than {validation['gt']}")
            if validation.get("ge") is not None and value < validation["ge"]:
                errors.append(f"'{key}' must be at least {validation['ge']}")
            if validation.get("lt") is not None and value >= validation["lt"]:
                errors.append(f"'{key}' must be less than {validation['lt']}")
            if validation.get("le") is not None and value > validation["le"]:
                errors.append(f"'{key}' must be at most {validation['le']}")

        elif qtype == "text":
            text_value = str(value)
            min_len = validation.get("min_length")
            max_len = validation.get("max_length")
            if min_len is not None and len(text_value) < min_len:
                errors.append(f"'{key}' must be at least {min_len} characters")
            if max_len is not None and len(text_value) > max_len:
                errors.append(f"'{key}' must be at most {max_len} characters")

        elif qtype == "boolean":
            if not isinstance(value, bool):
                errors.append(f"'{key}' must be a boolean")

        elif qtype == "select":
            options = question.get("options", [])
            if value not in options:
                errors.append(f"'{key}' must be one of {options}")

    if errors:
        raise IntakeValidationError("; ".join(errors))


def validate_intake(state: PlaybookDraftState) -> dict:
    """Validate the submitted answers against the playbook schema."""
    playbook = state["playbook"]
    answers = state["answers"]
    _validate_answers(playbook, answers)
    return {}


def build_query(state: PlaybookDraftState) -> dict:
    """Build a retrieval query from the intake answers."""
    playbook = state["playbook"]
    answers = state["answers"]
    parts = [f"Playbook: {playbook['title']}."]
    for question in playbook.get("intake_questions", []):
        key = question["key"]
        label = question["label"]
        value = answers.get(key)
        if value is not None:
            parts.append(f"{label}: {value}.")
    return {"query": " ".join(parts)}


async def retrieve_sources(state: PlaybookDraftState) -> dict:
    """Embed the query and retrieve relevant passages for the playbook's department."""
    settings = get_settings()
    db = state["db"]
    query = state["query"]
    department = state["playbook"]["department"]
    estimate = max(1, len(query) // 3)

    embedder = VoyageEmbedder()
    await reserve_usage(db, estimate)
    try:
        vectors, actual_tokens = embedder.embed_documents([query])
    except EmbeddingError:
        await release_reservation(db, estimate)
        await db.commit()
        raise

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
          AND sd.department = :department
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT 8
        """
    ).bindparams(bindparam("embedding", type_=Vector(settings.voyage_embedding_dimensions)))

    result = await db.execute(statement, {"embedding": vector, "department": department})
    passages = [dict(row) for row in result.mappings()]
    passages = deduplicate_passages(passages)
    return {"passages": passages}


async def generate_draft(state: PlaybookDraftState) -> dict:
    """Call the LLM with the playbook prompt template and retrieved sources."""
    playbook = state["playbook"]
    answers = state["answers"]
    passages = state.get("passages", [])
    system_prompt = playbook["prompt_template"]
    answers_json = json.dumps(answers, default=str)
    draft_content = await generate_playbook_draft(system_prompt, answers_json, passages)
    return {"draft_content": draft_content}


async def assemble_draft(state: PlaybookDraftState) -> dict:
    """Persist the case, draft, and citations, then return the response."""
    db = state["db"]
    playbook = state["playbook"]
    playbook_id = state["playbook_id"]
    answers = state["answers"]
    passages = state.get("passages", [])
    content = state["draft_content"]

    case_id = uuid4()
    draft_id = uuid4()

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
        for row in passages
    ]

    case_insert = await db.execute(
        text(
            """
            INSERT INTO cases (id, playbook_id, playbook_key, playbook_version, status, intake_answers)
            VALUES (:id, :playbook_id, :playbook_key, :playbook_version, 'draft_pending_review', CAST(:answers AS jsonb))
            RETURNING created_at
            """
        ),
        {
            "id": case_id,
            "playbook_id": playbook_id,
            "playbook_key": playbook["key"],
            "playbook_version": playbook["version"],
            "answers": json.dumps(answers, default=str),
        },
    )
    created_at = case_insert.scalar_one()

    await db.execute(
        text(
            """
            INSERT INTO drafts (id, case_id, version, status, content, disclaimer)
            VALUES (:id, :case_id, 1, 'pending_review', CAST(:content AS jsonb), :disclaimer)
            """
        ),
        {
            "id": draft_id,
            "case_id": case_id,
            "content": json.dumps(content),
            "disclaimer": DISCLAIMER,
        },
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

    response = GenericDraftResponse(
        case_id=str(case_id),
        draft_id=str(draft_id),
        case_status="draft_pending_review",
        draft_status="pending_review",
        playbook_key=playbook["key"],
        playbook_version=playbook["version"],
        created_at=created_at,
        disclaimer=DISCLAIMER,
        summary=content.get("summary", ""),
        checklist=content.get("checklist", []),
        risk_indicators=content.get("risk_indicators", []),
        missing_information=content.get("missing_information", []),
        recommended_next_steps=content.get("recommended_next_steps", []),
        sources=sources,
    )
    return {"response": response, "case_id": case_id, "draft_id": draft_id}


_builder = StateGraph(PlaybookDraftState)
_builder.add_node("load_playbook", load_playbook)
_builder.add_node("validate_intake", validate_intake)
_builder.add_node("build_query", build_query)
_builder.add_node("retrieve_sources", retrieve_sources)
_builder.add_node("generate_draft", generate_draft)
_builder.add_node("assemble_draft", assemble_draft)
_builder.add_edge(START, "load_playbook")
_builder.add_edge("load_playbook", "validate_intake")
_builder.add_edge("validate_intake", "build_query")
_builder.add_edge("build_query", "retrieve_sources")
_builder.add_edge("retrieve_sources", "generate_draft")
_builder.add_edge("generate_draft", "assemble_draft")
_builder.add_edge("assemble_draft", END)
playbook_draft_graph = _builder.compile()


async def run_playbook_draft(
    playbook_key: str,
    playbook_version: str,
    answers: dict[str, Any],
    db: AsyncSession,
) -> GenericDraftResponse:
    """Invoke the generic playbook draft graph and return its completed draft."""
    result = await playbook_draft_graph.ainvoke(
        {
            "playbook_key": playbook_key,
            "playbook_version": playbook_version,
            "answers": answers,
            "db": db,
        }
    )
    return result["response"]
