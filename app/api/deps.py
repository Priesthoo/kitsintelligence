"""
Shared FastAPI dependencies: database session, cache manager, current-user
resolution (JWT bearer or API key), and permission-checking guards used to
protect routes throughout the platform.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheManager, get_cache_manager
from app.core.logging import org_id_ctx, user_id_ctx
from app.core.security import TokenType, decode_token, verify_api_key
from app.db.session import get_db
from app.exceptions.base import AuthenticationError, InsufficientPermissionsError
from app.models.identity import User
from app.repositories.identity import APIKeyRepository, UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_cache() -> CacheManager:
    return get_cache_manager()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user: User | None = None

    if x_api_key:
        key_repo = APIKeyRepository(db)
        from app.core.security import hash_api_key
        from app.db.base import utcnow

        record = await key_repo.get_by_hash(hash_api_key(x_api_key))
        if record is None or (record.expires_at and record.expires_at < utcnow()):
            raise AuthenticationError("Invalid or expired API key")
        record.last_used_at = utcnow()
        await db.flush()
        user = await UserRepository(db).get_with_roles(record.user_id)
    elif credentials:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
        user = await UserRepository(db).get_with_roles(uuid.UUID(payload["sub"]))
    else:
        raise AuthenticationError("Authentication credentials were not provided")

    if user is None:
        raise AuthenticationError("User account not found")
    if user.status != "active":
        raise AuthenticationError("User account is not active")

    user_id_ctx.set(str(user.id))
    org_id_ctx.set(str(user.organization_id))
    request.state.current_user = user
    return user


async def get_current_active_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise InsufficientPermissionsError("This action requires superuser privileges")
    return user


def require_permissions(*required_codes: str) -> Callable:
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        granted = user.all_permission_codes()
        missing = [c for c in required_codes if c not in granted]
        if missing:
            raise InsufficientPermissionsError(
                f"Missing required permission(s): {', '.join(missing)}",
                details={"missing_permissions": missing},
            )
        return user

    return _checker


async def get_pagination(page: int = 1, page_size: int = 50) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return {"page": page, "page_size": page_size}