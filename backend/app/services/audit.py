"""Audit logging service.

Records user actions to the audit_logs table. All writes are fire-and-forget
(async tasks) so logging never blocks the request path.
"""
import logging
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("acme.audit")


def _get_client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def log_action(
    db: AsyncSession,
    action: str,
    user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    success: bool = True,
    request: Request | None = None,
) -> None:
    """Persist a single audit log entry."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
            success=success,
            details=details or {},
        )
        db.add(entry)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        # Never fail a user request because logging failed.
        logger.exception("Failed to write audit log: %s", exc)
        await db.rollback()


def log_action_async(
    db: AsyncSession,
    action: str,
    user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    success: bool = True,
    request: Request | None = None,
) -> None:
    """Schedule an audit log write in the background.

    Use this in endpoints where you do not want to await the commit.
    """
    import asyncio

    asyncio.create_task(
        log_action(
            db=db,
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            success=success,
            request=request,
        )
    )
