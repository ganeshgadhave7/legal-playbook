"""Alembic environment configured from backend environment variables."""
import os
from logging.config import fileConfig
from urllib.parse import urlparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the configured URL in memory only; do not write secrets into alembic.ini.
settings = get_settings()
raw_url = settings.async_database_url
if not raw_url:
    # Fallback to the public URL if the internal reference is empty/unset.
    raw_url = settings.database_public_url or os.getenv("DATABASE_PUBLIC_URL") or ""

if not raw_url:
    raise RuntimeError(
        "DATABASE_URL is empty or not set. "
        "Set DATABASE_URL=${{Postgres.DATABASE_URL}} in Railway Variables."
    )

# Sanitized log line for debugging (scheme + netloc, no credentials).
parsed = urlparse(raw_url)
safe_netloc = parsed.hostname or "unknown"
print(f"[alembic] Using database driver={parsed.scheme} host={safe_netloc}", flush=True)

config.set_main_option("sqlalchemy.url", raw_url.replace("%", "%%"))
target_metadata = None  # Initial migration is explicit SQLAlchemy Core operations.


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations using an async SQLAlchemy engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


def _run_sync_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
