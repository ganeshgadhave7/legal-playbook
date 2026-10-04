"""Helpers for cleaning up retrieval results."""
import hashlib
from typing import Any


def deduplicate_passages(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove passages with identical content, keeping the most similar copy.

    When the same policy has been uploaded multiple times, the same passage can
    appear under several source-document versions. This keeps one representative
    per unique content and preserves the citation with the highest similarity.
    """
    best_by_content: dict[str, dict[str, Any]] = {}
    for passage in passages:
        content = passage.get("content", "")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = best_by_content.get(content_hash)
        if existing is None or passage.get("similarity", 0) > existing.get("similarity", 0):
            best_by_content[content_hash] = passage
    return sorted(
        best_by_content.values(),
        key=lambda p: p.get("similarity", 0),
        reverse=True,
    )
