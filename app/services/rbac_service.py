"""Role & permission management (RBAC administration)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError, ValidationError
from app.models.identity import Permission, Role, User
from app.repositories.identity import PermissionRepository, RoleRepository
from app.schemas.identity import RoleCreate, RoleUpdate
from app.repositories.audit_service import AuditService


class RBACService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.roles = RoleRepository(session)
        self.permissions = PermissionRepository(session)
        self.audit = AuditService(session)

    async def list_permissions(self) -> list[Permission]:
        return await self.permissions.list_all()

    async def list_roles(self, organization_id: uuid.UUID) -> list[Role]:
        return await self.roles.list_for_org(organization_id)

    async def get_role(self, role_id: uuid.UUID, organization_id: uuid.UUID) -> Role:
        role = await self.roles.get_with_permissions(role_id)
        if role is None or role.organization_id != organization_id:
            raise NotFoundError("Role not found")
        return role

    async def create_role(self, organization_id: uuid.UUID, payload: RoleCreate, actor: User) -> Role:
        role = await self.roles.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name=payload.name,
            description=payload.description,
            is_system_role=False,
        )
        if payload.permission_ids:
            from sqlalchemy import select

            stmt = select(Permission).where(Permission.id.in_(payload.permission_ids))
            result = await self.session.execute(stmt)
            role.permissions = list(result.scalars().all())
            await self.session.flush()

        await self.audit.record(
            action="role.create",
            resource_type="role",
            resource_id=str(role.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return role

    async def update_role(
        self, role_id: uuid.UUID, organization_id: uuid.UUID, payload: RoleUpdate, actor: User
    ) -> Role:
        role = await self.get_role(role_id, organization_id)
        if role.is_system_role:
            raise ValidationError("System roles cannot be modified")

        if payload.name is not None:
            role.name = payload.name
        if payload.description is not None:
            role.description = payload.description
        if payload.permission_ids is not None:
            from sqlalchemy import select

            stmt = select(Permission).where(Permission.id.in_(payload.permission_ids))
            result = await self.session.execute(stmt)
            role.permissions = list(result.scalars().all())

        await self.session.flush()
        await self.audit.record(
            action="role.update",
            resource_type="role",
            resource_id=str(role.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return role

    async def delete_role(self, role_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        role = await self.get_role(role_id, organization_id)
        if role.is_system_role:
            raise ValidationError("System roles cannot be deleted")
        await self.roles.delete(role)