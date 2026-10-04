"""Voyage embedding client with strict dimension and usage safeguards."""
import logging

import voyageai

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when an embedding request cannot be safely completed."""


class VoyageEmbedder:
    """Generate vectors through Voyage while enforcing a local usage ceiling."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.voyage_api_key:
            raise EmbeddingError("VOYAGE_API_KEY is not configured")
        self.model = settings.voyage_embedding_model
        self.dimensions = settings.voyage_embedding_dimensions
        self.client = voyageai.Client(api_key=settings.voyage_api_key)

    def embed_documents(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Embed text passages as documents; return vectors and reported token usage."""
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("Embedding input must contain non-empty text")
        try:
            response = self.client.embed(
                texts,
                model=self.model,
                input_type="document",
            )
            vectors = response.embeddings
            # voyageai 0.5 exposes response usage as `total_tokens`.
            usage = getattr(response, "usage", None)
            token_count = getattr(usage, "total_tokens", None)
            if token_count is None:
                token_count = getattr(response, "total_tokens", None)
            if token_count is None:
                # Do not proceed when quota usage cannot be accounted for.
                raise EmbeddingError("Voyage response did not include token usage")
            if len(vectors) != len(texts):
                raise EmbeddingError("Voyage returned an unexpected number of vectors")
            if any(len(vector) != self.dimensions for vector in vectors):
                raise EmbeddingError(
                    f"Voyage vector dimension did not match configured {self.dimensions}"
                )
            return vectors, int(token_count)
        except EmbeddingError:
            raise
        except Exception as exc:
            logger.warning("Voyage embedding request failed (%s)", type(exc).__name__)
            raise EmbeddingError("Voyage embedding request failed") from exc
