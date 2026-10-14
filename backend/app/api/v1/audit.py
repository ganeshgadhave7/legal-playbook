"""Audit log query endpoints."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.auth import require_admin

router = APIRouter(prefix="/audit-logs", tags=["audit"], dependencies=[Depends(require_admin)])


class AuditLogItem(BaseModel):
    id: str
    created_at: datetime
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    user_agent: str | None
    success: bool
    details: dict | None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    exclude_action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> AuditLogListResponse:
    """List audit log entries. Admin-only."""
    # Build dynamic filters
    conditions = []
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if action:
        conditions.append("action = :action")
        params["action"] = action
    if exclude_action:
        conditions.append("action != :exclude_action")
        params["exclude_action"] = exclude_action
    if resource_type:
        conditions.append("resource_type = :resource_type")
        params["resource_type"] = resource_type
    if user_id:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_result = await db.execute(
        text(f"SELECT count(*) FROM audit_logs {where_clause}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT id, created_at, user_id, action, resource_type, resource_id,
                   ip_address, user_agent, success, details
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    items = [
        AuditLogItem(
            id=str(row["id"]),
            created_at=row["created_at"],
            user_id=str(row["user_id"]) if row["user_id"] else None,
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            success=row["success"],
            details=row["details"] or {},
        )
        for row in result.mappings()
    ]
    return AuditLogListResponse(items=items, total=total)
