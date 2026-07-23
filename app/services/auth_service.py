"""
Authentication service: registration, login (with lockout + MFA), token
refresh/rotation, logout/revocation, password reset flow, and MFA
enrollment. This is the single source of truth for authentication business
rules; the API layer only translates HTTP <-> these calls.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pyotp

from app.core.cache import CacheManager
from app.core.config import settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    create_special_token,
    decode_token,
    generate_secure_random_code,
    hash_password,
    verify_password,
)
from app.db.base import utcnow
from app.exceptions.base import (
    AlreadyExistsError,
    AuthenticationError,
    InvalidCredentialsError,
    MFARequiredError,
    NotFoundError,
    TokenInvalidError,
    ValidationError,
)
from app.models.identity import Organization, OrganizationPlan, User, UserStatus
from app.repositories.identity import (
    OrganizationRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.schemas.identity import LoginRequest, RegisterRequest, TokenPair
from app.services.audit_service import AuditService
from sqlalchemy.ext.asyncio import AsyncSession

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


class AuthService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.users = UserRepository(session)
        self.orgs = OrganizationRepository(session)
        self.roles = RoleRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.audit = AuditService(session)

    async def register(
        self, payload: RegisterRequest, *, ip_address: str | None = None
    ) -> tuple[User, Organization]:
        if await self.orgs.get_by_slug(payload.organization_slug):
            raise AlreadyExistsError("Organization slug is already taken")
        if await self.users.get_by_email(payload.email):
            raise AlreadyExistsError("A user with this email already exists")

        org = await self.orgs.create(
            id=uuid.uuid4(),
            name=payload.organization_name,
            slug=payload.organization_slug,
            plan=OrganizationPlan.TRIAL.value,
        )

        owner_role = await self.roles.create(
            id=uuid.uuid4(),
            organization_id=org.id,
            name="Owner",
            description="Full administrative access to the organization",
            is_system_role=True,
        )
        from app.repositories.identity import PermissionRepository

        all_perms = await PermissionRepository(self.session).list_all()
        owner_role.permissions = all_perms
        await self.session.flush()

        user = await self.users.create(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=payload.email.lower(),
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            status=UserStatus.ACTIVE.value,
            is_email_verified=False,
        )
        user.roles.append(owner_role)
        await self.session.flush()

        await self.audit.record(
            action="user.register",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=org.id,
            actor_user_id=user.id,
            ip_address=ip_address,
        )
        return user, org

    async def authenticate(
        self, payload: LoginRequest, *, ip_address: str | None = None, user_agent: str | None = None
    ) -> tuple[User, TokenPair]:
        user = await self.users.get_by_email(payload.email)
        if user is None:
            raise InvalidCredentialsError("Invalid email or password")

        if user.is_locked:
            raise AuthenticationError(
                "Account temporarily locked due to repeated failed login attempts",
                error_code="account_locked",
            )

        if user.status != UserStatus.ACTIVE.value:
            raise AuthenticationError("Account is not active", error_code="account_inactive")

        if not verify_password(payload.password, user.hashed_password):
            await self._register_failed_login(user)
            raise InvalidCredentialsError("Invalid email or password")

        if user.mfa_enabled:
            if not payload.mfa_code:
                raise MFARequiredError("MFA verification code required")
            totp = pyotp.TOTP(user.mfa_secret)
            if not totp.verify(payload.mfa_code, valid_window=1):
                await self._register_failed_login(user)
                raise InvalidCredentialsError("Invalid MFA code")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = utcnow()
        user.last_login_ip = ip_address
        await self.session.flush()

        tokens = await self._issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)

        await self.audit.record(
            action="user.login",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=user.organization_id,
            actor_user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user, tokens

    async def _register_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        await self.session.flush()

    async def _issue_token_pair(
        self, user: User, *, ip_address: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        access_token, _ = create_access_token(
            str(user.id),
            extra_claims={
                "org_id": str(user.organization_id),
                "permissions": sorted(user.all_permission_codes()),
                "is_superuser": user.is_superuser,
            },
        )
        refresh_token, jti = create_refresh_token(str(user.id))

        await self.refresh_tokens.create(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        jti = payload.get("jti")
        record = await self.refresh_tokens.get_by_jti(jti) if jti else None
        if record is None or record.revoked:
            raise TokenInvalidError("Refresh token has been revoked or does not exist")
        if record.expires_at < utcnow():
            raise TokenInvalidError("Refresh token has expired")

        user = await self.users.get_with_roles(uuid.UUID(payload["sub"]))
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise AuthenticationError("User is not active")

        record.revoked = True
        record.revoked_at = utcnow()
        await self.session.flush()

        return await self._issue_token_pair(user, ip_address=record.ip_address, user_agent=record.user_agent)

    async def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except AuthenticationError:
            return
        jti = payload.get("jti")
        if jti:
            record = await self.refresh_tokens.get_by_jti(jti)
            if record and not record.revoked:
                record.revoked = True
                record.revoked_at = utcnow()
                await self.session.flush()

    async def logout_all_sessions(self, user_id: uuid.UUID) -> None:
        await self.refresh_tokens.revoke_all_for_user(user_id)

    async def request_password_reset(self, email: str) -> str | None:
        user = await self.users.get_by_email(email)
        if user is None:
            return None
        token, _ = create_special_token(str(user.id), TokenType.RESET_PASSWORD, timedelta(hours=1))
        await self.cache.set(f"pwd_reset:{user.id}", token, ttl_seconds=3600)
        return token

    async def reset_password(self, token: str, new_password: str) -> None:
        payload = decode_token(token, expected_type=TokenType.RESET_PASSWORD)
        user_id = uuid.UUID(payload["sub"])
        cached = await self.cache.get(f"pwd_reset:{user_id}")
        if cached != token:
            raise TokenInvalidError("Password reset token is invalid or has already been used")

        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")

        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.session.flush()
        await self.cache.delete(f"pwd_reset:{user_id}")
        await self.refresh_tokens.revoke_all_for_user(user_id)

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError("Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        await self.session.flush()
        await self.refresh_tokens.revoke_all_for_user(user.id)

    # ------------------------------------------------------------------ #
    # MFA
    # ------------------------------------------------------------------ #
    async def initiate_mfa_setup(self, user: User) -> tuple[str, str, list[str]]:
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=settings.MFA_ISSUER_NAME)
        backup_codes = [generate_secure_random_code(8) for _ in range(10)]
        await self.cache.set_json(
            f"mfa_setup:{user.id}",
            {"secret": secret, "backup_codes": backup_codes},
            ttl_seconds=600,
        )
        return secret, uri, backup_codes

    async def confirm_mfa_setup(self, user: User, code: str) -> None:
        pending = await self.cache.get_json(f"mfa_setup:{user.id}")
        if not pending:
            raise ValidationError("No pending MFA setup found; please restart enrollment")
        totp = pyotp.TOTP(pending["secret"])
        if not totp.verify(code, valid_window=1):
            raise ValidationError("Invalid verification code")
        user.mfa_secret = pending["secret"]
        user.mfa_enabled = True
        await self.session.flush()
        await self.cache.delete(f"mfa_setup:{user.id}")

    async def disable_mfa(self, user: User, code: str) -> None:
        if not user.mfa_enabled or not user.mfa_secret:
            raise ValidationError("MFA is not currently enabled")
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(code, valid_window=1):
            raise ValidationError("Invalid verification code")
        user.mfa_enabled = False
        user.mfa_secret = None
        await self.session.flush()