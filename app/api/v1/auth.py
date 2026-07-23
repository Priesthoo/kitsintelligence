"""Authentication endpoints: register, login, refresh, logout, password reset, MFA."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_current_user, get_db
from app.core.cache import CacheManager
from app.models.identity import User
from app.schemas.identity import (
    ForgotPasswordRequest,
    LoginRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    PasswordChange,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserRead,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> User:
    service = AuthService(db, cache)
    user, _org = await service.register(payload, ip_address=_client_ip(request))
    return user


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> TokenPair:
    service = AuthService(db, cache)
    _user, tokens = await service.authenticate(
        payload, ip_address=_client_ip(request), user_agent=request.headers.get("User-Agent")
    )
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db), cache: CacheManager = Depends(get_cache)
) -> TokenPair:
    service = AuthService(db, cache)
    return await service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db), cache: CacheManager = Depends(get_cache)
) -> None:
    service = AuthService(db, cache)
    await service.logout(payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> None:
    service = AuthService(db, cache)
    await service.logout_all_sessions(user.id)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db), cache: CacheManager = Depends(get_cache)
) -> dict:
    service = AuthService(db, cache)
    await service.request_password_reset(payload.email)
    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db), cache: CacheManager = Depends(get_cache)
) -> None:
    service = AuthService(db, cache)
    await service.reset_password(payload.token, payload.new_password)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> None:
    service = AuthService(db, cache)
    await service.change_password(user, payload.current_password, payload.new_password)


@router.get("/me", response_model=UserRead)
async def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> MFASetupResponse:
    service = AuthService(db, cache)
    secret, uri, backup_codes = await service.initiate_mfa_setup(user)
    return MFASetupResponse(secret=secret, provisioning_uri=uri, backup_codes=backup_codes)


@router.post("/mfa/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_mfa(
    payload: MFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> None:
    service = AuthService(db, cache)
    await service.confirm_mfa_setup(user, payload.code)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    payload: MFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> None:
    service = AuthService(db, cache)
    await service.disable_mfa(user, payload.code)