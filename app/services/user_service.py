"""User management: invitation, profile updates, admin operations, API keys."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenType,
    create_special_token,
    decode_token,
    generate_api_key,
    hash_password,
)
from app.db.base import utcnow
from app.exceptions.base import AlreadyExistsError, NotFoundError, ValidationError
from app.models.identity import User, UserStatus
from app.repositories.identity import APIKeyRepository, OrganizationRepository, RoleRepository, UserRepository
from app.schemas.identity import APIKeyCreate, UserAdminUpdate, UserInvite, UserUpdate
from app.repositories.audit_service import AuditService


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.orgs = OrganizationRepository(session)
        self.roles = RoleRepository(session)
        self.api_keys = APIKeyRepository(session)
        self.audit = AuditService(session)

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_with_roles(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def list_for_org(
        self, organization_id: uuid.UUID, *, page: int = 1, page_size: int = 50, status: str | None = None
    ) -> tuple[list[User], int]:
        offset = (page - 1) * page_size
        items = await self.users.list_for_org(organization_id, offset=offset, limit=page_size, status=status)
        total = await self.users.count(organization_id=organization_id, **({"status": status} if status else {}))
        return items, total

    async def invite_user(self, organization_id: uuid.UUID, payload: UserInvite, actor: User) -> User:
        org = await self.orgs.get(organization_id)
        if org is None:
            raise NotFoundError("Organization not found")

        existing = await self.users.get_by_email(payload.email)
        if existing:
            raise AlreadyExistsError("A user with this email already exists")

        active_count = await self.users.count_active_for_org(organization_id)
        if active_count >= org.max_users:
            raise ValidationError(f"Organization has reached its user limit of {org.max_users}")

        temp_password = hash_password(uuid.uuid4().hex)
        user = await self.users.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            email=payload.email.lower(),
            hashed_password=temp_password,
            full_name=payload.full_name,
            status=UserStatus.INVITED.value,
            is_email_verified=False,
        )

        if payload.role_ids:
            roles = await self.roles.get_by_ids(payload.role_ids)
            user.roles.extend([r for r in roles if r.organization_id == organization_id])
            await self.session.flush()

        invite_token, _ = create_special_token(str(user.id), TokenType.EMAIL_VERIFY, timedelta(days=7))

        await self.audit.record(
            action="user.invite",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return user

    async def accept_invite(self, token: str, password: str) -> User:
        payload = decode_token(token, expected_type=TokenType.EMAIL_VERIFY)
        user = await self.users.get(uuid.UUID(payload["sub"]))
        if user is None:
            raise NotFoundError("Invitation not found")
        if user.status != UserStatus.INVITED.value:
            raise ValidationError("This invitation has already been used or is no longer valid")

        user.hashed_password = hash_password(password)
        user.status = UserStatus.ACTIVE.value
        user.is_email_verified = True
        await self.session.flush()
        return user

    async def update_profile(self, user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(user, key, value)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def admin_update(self, user_id: uuid.UUID, payload: UserAdminUpdate, actor: User) -> User:
        user = await self.get_by_id(user_id)
        if payload.status is not None:
            user.status = payload.status
        if payload.is_superuser is not None:
            if not actor.is_superuser:
                raise ValidationError("Only a superuser can grant superuser privileges")
            user.is_superuser = payload.is_superuser
        if payload.role_ids is not None:
            roles = await self.roles.get_by_ids(payload.role_ids)
            user.roles = [r for r in roles if r.organization_id == user.organization_id]
        await self.session.flush()

        await self.audit.record(
            action="user.admin_update",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=user.organization_id,
            actor_user_id=actor.id,
        )
        return user

    async def deactivate(self, user_id: uuid.UUID, actor: User) -> User:
        user = await self.get_by_id(user_id)
        user.status = UserStatus.DEACTIVATED.value
        await self.session.flush()
        await self.audit.record(
            action="user.deactivate",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=user.organization_id,
            actor_user_id=actor.id,
        )
        return user

    # ------------------------------------------------------------------ #
    # API Keys
    # ------------------------------------------------------------------ #
    async def create_api_key(self, user: User, payload: APIKeyCreate) -> tuple[User, str, object]:
        raw_key, key_hash, prefix = generate_api_key()
        api_key = await self.api_keys.create(
            id=uuid.uuid4(),
            user_id=user.id,
            organization_id=user.organization_id,
            name=payload.name,
            key_hash=key_hash,
            key_prefix=prefix,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        return user, raw_key, api_key

    async def list_api_keys(self, user: User) -> list:
        return await self.api_keys.list_for_user(user.id)

    async def revoke_api_key(self, user: User, api_key_id: uuid.UUID) -> None:
        key = await self.api_keys.get(api_key_id)
        if key is None or key.user_id != user.id:
            raise NotFoundError("API key not found")
        key.is_active = False
        await self.session.flush()