"""Citation verifier: checks whether generated draft claims are grounded in retrieved passages."""
import logging
import math
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.usage_budget import (
    UsageBudgetExceeded,
    reconcile_usage,
    release_reservation,
    reserve_usage,
)
from app.services.voyage_embeddings import EmbeddingError, VoyageEmbedder

logger = logging.getLogger(__name__)


class ClaimScore(BaseModel):
    """Verification result for a single claim."""

    claim: str
    best_similarity: float = Field(ge=0.0, le=1.0)
    supported: bool
    best_passage_index: int | None = None


class CitationVerificationReport(BaseModel):
    """Report produced after comparing draft claims to retrieved passages."""

    status: str  # verified | verified_with_warnings | failed
    threshold: float
    supported_claims: int
    unsupported_claims: int
    low_confidence_claims: int
    claims: list[ClaimScore]
    unsupported_details: list[str]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _extract_claims(content: dict[str, Any]) -> list[str]:
    """Pull verifiable claims out of a structured draft.

    We verify list items and individual sentences from the summary.
    We do *not* re-verify items already in missing_information because those
    are explicitly admitted unknowns.
    """
    claims: list[str] = []

    for field in ("checklist", "risk_indicators", "recommended_next_steps"):
        items = content.get(field) or []
        for item in items:
            text = str(item).strip()
            if text and len(text) > 5:
                claims.append(text)

    summary = str(content.get("summary", "")).strip()
    if summary:
        # Split summary into sentences, ignoring trivial fragments.
        sentences = re.split(r"(?<=[.!?])\s+", summary)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 10:
                claims.append(sentence)

    return claims


def _move_unsupported_claims(
    content: dict[str, Any],
    unsupported_claims: list[str],
) -> dict[str, Any]:
    """Return a new content dict with unsupported list claims moved to missing_information."""
    updated = {k: list(v) if isinstance(v, list) else v for k, v in content.items()}
    missing = list(updated.get("missing_information", []) or [])

    for field in ("checklist", "risk_indicators", "recommended_next_steps"):
        kept: list[Any] = []
        for item in updated.get(field, []) or []:
            if str(item).strip() in unsupported_claims:
                missing.append(f"Could not verify against approved sources: {item}")
            else:
                kept.append(item)
        updated[field] = kept

    updated["missing_information"] = missing
    return updated


async def verify_draft_citations(
    content: dict[str, Any],
    passages: list[dict[str, Any]],
    db: Any | None = None,
) -> tuple[dict[str, Any], CitationVerificationReport]:
    """Verify that draft claims are supported by retrieved passages.

    Returns the (possibly modified) content and a verification report.
    Unsupported list-item claims are moved into missing_information.
    """
    settings = get_settings()
    threshold = settings.citation_similarity_threshold
    claims = _extract_claims(content)

    if not claims:
        report = CitationVerificationReport(
            status="verified",
            threshold=threshold,
            supported_claims=0,
            unsupported_claims=0,
            low_confidence_claims=0,
            claims=[],
            unsupported_details=[],
        )
        return content, report

    if not passages:
        report = CitationVerificationReport(
            status="failed",
            threshold=threshold,
            supported_claims=0,
            unsupported_claims=len(claims),
            low_confidence_claims=0,
            claims=[
                ClaimScore(claim=claim, best_similarity=0.0, supported=False)
                for claim in claims
            ],
            unsupported_details=[
                "No approved source passages were retrieved; all claims are unsupported."
            ],
        )
        updated = _move_unsupported_claims(content, claims)
        return updated, report

    passage_texts = [str(p.get("content", "")).strip() for p in passages]
    all_texts = claims + passage_texts
    estimated_tokens = sum(max(1, len(text) // 3) for text in all_texts)

    try:
        embedder = VoyageEmbedder()
        if db is not None:
            await reserve_usage(db, estimated_tokens)
        vectors, actual_tokens = embedder.embed_documents(all_texts)
        if db is not None:
            await reconcile_usage(db, estimated_tokens, actual_tokens)
            await db.commit()
    except UsageBudgetExceeded:
        if db is not None:
            await db.rollback()
        raise
    except EmbeddingError:
        if db is not None:
            await release_reservation(db, estimated_tokens)
            await db.commit()
        logger.warning("Citation verifier could not embed claims/passages")
        report = CitationVerificationReport(
            status="failed",
            threshold=threshold,
            supported_claims=0,
            unsupported_claims=len(claims),
            low_confidence_claims=0,
            claims=[
                ClaimScore(claim=claim, best_similarity=0.0, supported=False)
                for claim in claims
            ],
            unsupported_details=["Embedding service unavailable; could not verify citations."],
        )
        updated = _move_unsupported_claims(content, claims)
        return updated, report

    claim_vectors = vectors[: len(claims)]
    passage_vectors = vectors[len(claims) :]

    scored_claims: list[ClaimScore] = []
    unsupported: list[str] = []
    low_confidence_threshold = max(0.0, threshold - 0.15)
    supported_count = 0
    low_confidence_count = 0

    for idx, claim_vector in enumerate(claim_vectors):
        best_score = 0.0
        best_passage_idx: int | None = None
        for p_idx, passage_vector in enumerate(passage_vectors):
            score = _cosine_similarity(claim_vector, passage_vector)
            if score > best_score:
                best_score = score
                best_passage_idx = p_idx

        supported = best_score >= threshold
        if supported:
            supported_count += 1
        elif best_score >= low_confidence_threshold:
            low_confidence_count += 1

        scored_claims.append(
            ClaimScore(
                claim=claims[idx],
                best_similarity=round(best_score, 4),
                supported=supported,
                best_passage_index=best_passage_idx,
            )
        )
        if not supported:
            unsupported.append(claims[idx])

    status = "verified"
    if unsupported:
        status = "verified_with_warnings"
    if not supported_count and unsupported:
        status = "failed"

    report = CitationVerificationReport(
        status=status,
        threshold=threshold,
        supported_claims=supported_count,
        unsupported_claims=len(unsupported),
        low_confidence_claims=low_confidence_count,
        claims=scored_claims,
        unsupported_details=[f"Unsupported: {u}" for u in unsupported],
    )

    updated_content = _move_unsupported_claims(content, unsupported)
    return updated_content, report
