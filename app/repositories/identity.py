"""Repositories for Organization, Team, User, Role, Permission, RefreshToken, APIKey."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.identity import (
    APIKey,
    Organization,
    Permission,
    RefreshToken,
    Role,
    Team,
    User,
    team_members,
)
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    async def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug, Organization.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class TeamRepository(BaseRepository[Team]):
    model = Team

    async def list_for_org(self, organization_id: uuid.UUID) -> list[Team]:
        stmt = (
            select(Team)
            .where(Team.organization_id == organization_id, Team.is_deleted.is_(False))
            .options(selectinload(Team.members))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def add_member(self, team: Team, user: User) -> None:
        if user not in team.members:
            team.members.append(user)
            await self.session.flush()

    async def remove_member(self, team: Team, user: User) -> None:
        if user in team.members:
            team.members.remove(user)
            await self.session.flush()


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    async def get_by_codes(self, codes: list[str]) -> list[Permission]:
        if not codes:
            return []
        pairs = [tuple(c.split(":", 1)) for c in codes if ":" in c]
        results: list[Permission] = []
        for resource, action in pairs:
            stmt = select(Permission).where(Permission.resource == resource, Permission.action == action)
            r = await self.session.execute(stmt)
            perm = r.scalar_one_or_none()
            if perm:
                results.append(perm)
        return results

    async def list_all(self) -> list[Permission]:
        result = await self.session.execute(select(Permission).order_by(Permission.resource, Permission.action))
        return list(result.scalars().all())


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_with_permissions(self, role_id: uuid.UUID) -> Role | None:
        stmt = (
            select(Role)
            .where(Role.id == role_id, Role.is_deleted.is_(False))
            .options(selectinload(Role.permissions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: uuid.UUID) -> list[Role]:
        stmt = (
            select(Role)
            .where(Role.organization_id == organization_id, Role.is_deleted.is_(False))
            .options(selectinload(Role.permissions))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_by_ids(self, role_ids: list[uuid.UUID]) -> list[Role]:
        if not role_ids:
            return []
        stmt = select(Role).where(Role.id.in_(role_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(User)
            .where(User.email == email.lower(), User.is_deleted.is_(False))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id, User.is_deleted.is_(False))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: uuid.UUID, *, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> list[User]:
        stmt = select(User).where(User.organization_id == organization_id, User.is_deleted.is_(False))
        if status:
            stmt = stmt.where(User.status == status)
        stmt = stmt.options(selectinload(User.roles)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_active_for_org(self, organization_id: uuid.UUID) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(User).where(
            User.organization_id == organization_id,
            User.is_deleted.is_(False),
            User.status == "active",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        from app.db.base import utcnow

        stmt = select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        result = await self.session.execute(stmt)
        for token in result.scalars().all():
            token.revoked = True
            token.revoked_at = utcnow()
        await self.session.flush()


class APIKeyRepository(BaseRepository[APIKey]):
    model = APIKey

    async def get_by_hash(self, key_hash: str) -> APIKey | None:
        stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[APIKey]:
        stmt = select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())