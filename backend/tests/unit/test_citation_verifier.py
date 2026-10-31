"""Unit tests for the citation verifier."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.citation_verifier import verify_draft_citations


def _make_embedder(claim_vectors: list[list[float]], passage_vectors: list[list[float]], token_count: int = 10):
    """Return a mock VoyageEmbedder that returns deterministic vectors."""
    mock = MagicMock()

    def embed_documents(texts: list[str]) -> tuple[list[list[float]], int]:
        claims = texts[: len(claim_vectors)]
        passages = texts[len(claim_vectors) :]
        assert len(claims) == len(claim_vectors)
        assert len(passages) == len(passage_vectors)
        return claim_vectors + passage_vectors, token_count

    mock.embed_documents = embed_documents
    return mock


def _same_vector(dim: int) -> list[float]:
    return [1.0] * dim


def _orthogonal_vector(dim: int, index: int) -> list[float]:
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


@pytest.mark.asyncio
async def test_supported_claim_passes_verification():
    content = {
        "summary": "Vendor needs review.",
        "checklist": ["Require privacy review."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    passages = [{"content": "Privacy review is required for vendors handling personal data."}]
    dim = 8

    with patch(
        "app.services.citation_verifier.VoyageEmbedder",
        return_value=_make_embedder([_same_vector(dim), _same_vector(dim)], [_same_vector(dim)]),
    ):
        updated, report = await verify_draft_citations(content, passages)

    assert report.supported_claims == 2
    assert report.unsupported_claims == 0
    assert report.status == "verified"
    assert "Require privacy review." in updated["checklist"]


@pytest.mark.asyncio
async def test_unsupported_claim_is_moved_to_missing_information():
    content = {
        "summary": "Vendor needs review.",
        "checklist": ["Require a $5M insurance policy."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }
    passages = [{"content": "Privacy review is required for vendors handling personal data."}]
    dim = 8

    with patch(
        "app.services.citation_verifier.VoyageEmbedder",
        return_value=_make_embedder(
            [_orthogonal_vector(dim, 0), _orthogonal_vector(dim, 2)],
            [_orthogonal_vector(dim, 1)],
        ),
    ):
        updated, report = await verify_draft_citations(content, passages)

    assert report.supported_claims == 0
    assert report.unsupported_claims == 2
    assert report.status == "failed"
    assert "$5M insurance policy" not in updated["checklist"]
    assert any("$5M insurance policy" in item for item in updated["missing_information"])


@pytest.mark.asyncio
async def test_no_passages_marks_all_claims_unsupported():
    content = {
        "summary": "Summary.",
        "checklist": ["Action one.", "Action two."],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }

    updated, report = await verify_draft_citations(content, [])

    assert report.status == "failed"
    assert report.unsupported_claims == 2
    assert len(updated["missing_information"]) == 2


@pytest.mark.asyncio
async def test_empty_draft_is_verified():
    content = {
        "summary": "",
        "checklist": [],
        "risk_indicators": [],
        "missing_information": [],
        "recommended_next_steps": [],
    }

    updated, report = await verify_draft_citations(content, [])

    assert report.status == "verified"
    assert report.supported_claims == 0
    assert updated == content
