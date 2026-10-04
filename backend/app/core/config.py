"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings; secrets are read from environment, never source code."""

    database_url: str
    database_public_url: str | None = None
    voyage_api_key: str | None = None
    voyage_embedding_model: str = "voyage-4"
    voyage_embedding_dimensions: int = 1024

    # LLM configuration (OpenCode-compatible by default)
    llm_api_key: str | None = None
    llm_base_url: str = "https://opencode.ai/zen/go/v1"
    llm_model: str = "kimi-k2.6"

    app_env: str = "local"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_all: bool = False
    upload_storage_path: Path = Path("storage/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    voyage_token_budget: int = 180_000_000
    voyage_tokens_used: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        """Convert Railway's postgres:// or postgresql:// URL to asyncpg driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_allow_all:
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
