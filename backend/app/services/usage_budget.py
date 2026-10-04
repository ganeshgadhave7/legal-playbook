"""Persistent local ledger and cap for Voyage embedding token usage."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


class UsageBudgetExceeded(RuntimeError):
    """Raised when a request would exceed the configured local token ceiling."""


def check_local_budget(used: int, additional: int) -> None:
    """Fail closed if the conservative local token budget would be exceeded."""
    budget = get_settings().voyage_token_budget
    if additional < 0 or used < 0 or used + additional > budget:
        raise UsageBudgetExceeded("Voyage local token budget would be exceeded")


async def read_usage(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT tokens_used FROM embedding_usage WHERE id = 1"))
    value = result.scalar_one_or_none()
    return int(value or 0)


async def reserve_usage(session: AsyncSession, estimated_tokens: int) -> int:
    """Atomically reserve estimated usage before sending text to Voyage."""
    budget = get_settings().voyage_token_budget
    # Ensure singleton row exists even if local development data was cleared.
    await session.execute(
        text("INSERT INTO embedding_usage (id, tokens_used) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
    )
    result = await session.execute(
        text(
            """
            UPDATE embedding_usage
            SET tokens_used = tokens_used + :amount, updated_at = now()
            WHERE id = 1 AND tokens_used + :amount <= :budget
            RETURNING tokens_used
            """
        ),
        {"amount": estimated_tokens, "budget": budget},
    )
    new_total = result.scalar_one_or_none()
    if new_total is None:
        raise UsageBudgetExceeded("Voyage local token budget would be exceeded")
    return int(new_total)


async def reconcile_usage(session: AsyncSession, estimated_tokens: int, actual_tokens: int) -> int:
    """Adjust reservation to provider-reported usage; reject quota overrun."""
    budget = get_settings().voyage_token_budget
    result = await session.execute(
        text(
            """
            UPDATE embedding_usage
            SET tokens_used = tokens_used - :estimated + :actual, updated_at = now()
            WHERE id = 1 AND tokens_used - :estimated + :actual <= :budget
            RETURNING tokens_used
            """
        ),
        {"estimated": estimated_tokens, "actual": actual_tokens, "budget": budget},
    )
    new_total = result.scalar_one_or_none()
    if new_total is None:
        raise UsageBudgetExceeded("Provider-reported usage exceeds local Voyage budget")
    return int(new_total)


async def release_reservation(session: AsyncSession, estimated_tokens: int) -> None:
    await session.execute(
        text(
            """
            UPDATE embedding_usage
            SET tokens_used = GREATEST(0, tokens_used - :estimated), updated_at = now()
            WHERE id = 1
            """
        ),
        {"estimated": estimated_tokens},
    )
