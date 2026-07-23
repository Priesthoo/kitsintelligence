"""Organization lifecycle management."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError
from app.models.identity import Organization, User
from app.repositories.identity import OrganizationRepository
from app.schemas.identity import OrganizationUpdate
from app.repositories.audit_service import AuditService


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orgs = OrganizationRepository(session)
        self.audit = AuditService(session)

    async def get(self, organization_id: uuid.UUID) -> Organization:
        org = await self.orgs.get(organization_id)
        if org is None:
            raise NotFoundError("Organization not found")
        return org

    async def update(self, organization_id: uuid.UUID, payload: OrganizationUpdate, actor: User) -> Organization:
        org = await self.get(organization_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(org, key, value)
        await self.session.flush()
        await self.audit.record(
            action="organization.update",
            resource_type="organization",
            resource_id=str(org.id),
            organization_id=org.id,
            actor_user_id=actor.id,
            metadata=data,
        )
        return org

    async def deactivate(self, organization_id: uuid.UUID, actor: User) -> Organization:
        org = await self.get(organization_id)
        org.is_active = False
        await self.session.flush()
        await self.audit.record(
            action="organization.deactivate",
            resource_type="organization",
            resource_id=str(org.id),
            organization_id=org.id,
            actor_user_id=actor.id,
        )
        return org