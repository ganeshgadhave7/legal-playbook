"""Metadata-filtered semantic retrieval over ready source documents."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.user import User
from app.services.auth import require_user
from app.services.usage_budget import (
    UsageBudgetExceeded,
    read_usage,
    reserve_usage,
    reconcile_usage,
    release_reservation,
)
from app.services.retrieval_utils import deduplicate_passages
from app.services.voyage_embeddings import EmbeddingError, VoyageEmbedder

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    department: str | None = Field(default=None, max_length=120)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedPassage(BaseModel):
    chunk_id: UUID
    source_document_id: UUID
    title: str
    document_code: str | None
    version: str
    section: str | None
    page_number: int | None
    content: str
    similarity: float


class RetrievalResponse(BaseModel):
    query: str
    passages: list[RetrievedPassage]
    token_budget_remaining: int


@router.post("", response_model=RetrievalResponse)
async def retrieve_passages(
    request: RetrievalRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user),
) -> RetrievalResponse:
    """Embed a query and retrieve only passages from successfully indexed sources."""
    embedder = VoyageEmbedder()
    estimated_tokens = max(1, len(request.query) // 3)
    try:
        await reserve_usage(db, estimated_tokens)
        vectors, actual_tokens = embedder.embed_documents([request.query])
        await reconcile_usage(db, estimated_tokens, actual_tokens)
        await db.commit()
    except UsageBudgetExceeded as exc:
        await db.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmbeddingError as exc:
        await release_reservation(db, estimated_tokens)
        await db.commit()
        raise HTTPException(status_code=502, detail="Could not embed search query") from exc

    vector = vectors[0]
    dimensions = get_settings().voyage_embedding_dimensions
    if len(vector) != dimensions:
        raise HTTPException(status_code=502, detail="Unexpected embedding vector dimensions")

    conditions = ["sd.status = 'ready'"]
    params: dict[str, object] = {"embedding": vector, "top_k": request.top_k}
    if request.department:
        conditions.append("sd.department = :department")
        params["department"] = request.department.strip()

    retrieval_query = text(
            f"""
            SELECT dc.id AS chunk_id,
                   sd.id AS source_document_id,
                   sd.title,
                   sd.document_code,
                   sd.version,
                   dc.section,
                   dc.page_number,
                   dc.content,
                   1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM document_chunks dc
            JOIN source_documents sd ON sd.id = dc.source_document_id
            WHERE {' AND '.join(conditions)}
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        ).bindparams(bindparam("embedding", type_=Vector(dimensions)))
    result = await db.execute(retrieval_query, params)
    passages = [RetrievedPassage(**dict(row)) for row in result.mappings()]
    # The same content may be indexed under multiple source versions.
    passages = [RetrievedPassage(**p) for p in deduplicate_passages([p.model_dump() for p in passages])]
    tokens_used = await read_usage(db)
    remaining = max(0, get_settings().voyage_token_budget - tokens_used)
    return RetrievalResponse(query=request.query, passages=passages, token_budget_remaining=remaining)
