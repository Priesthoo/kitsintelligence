"""Centralized audit trail writer. Every state-changing service call routes through here."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.identity import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata or {},
            created_at=utcnow(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_org(
        self, organization_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> list[AuditLog]:
        from sqlalchemy import select

        stmt = (
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())