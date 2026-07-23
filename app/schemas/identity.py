"""Pydantic v2 request/response DTOs for the identity domain."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings


# --------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------- #
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(ORMBase):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# --------------------------------------------------------------------- #
# Organization
# --------------------------------------------------------------------- #
class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    plan: str = "trial"


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    country_code: str | None = None
    plan: str | None = None
    max_users: int | None = Field(default=None, gt=0)
    settings_json: dict | None = None
    is_active: bool | None = None


class OrganizationRead(ORMBase):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    country_code: str | None
    max_users: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------- #
# Team
# --------------------------------------------------------------------- #
class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None


class TeamRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    member_count: int = 0


class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID


# --------------------------------------------------------------------- #
# Permission / Role
# --------------------------------------------------------------------- #
class PermissionRead(ORMBase):
    id: uuid.UUID
    resource: str
    action: str
    description: str | None

    @property
    def code(self) -> str:
        return f"{self.resource}:{self.action}"


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permission_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None


class RoleRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    is_system_role: bool
    permissions: list[PermissionRead] = Field(default_factory=list)


# --------------------------------------------------------------------- #
# User
# --------------------------------------------------------------------- #
_PASSWORD_UPPER = re.compile(r"[A-Z]")
_PASSWORD_LOWER = re.compile(r"[a-z]")
_PASSWORD_DIGIT = re.compile(r"\d")
_PASSWORD_SPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]")


def validate_password_strength(password: str) -> str:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    if not _PASSWORD_UPPER.search(password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not _PASSWORD_LOWER.search(password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not _PASSWORD_DIGIT.search(password):
        raise ValueError("Password must contain at least one digit")
    if not _PASSWORD_SPECIAL.search(password):
        raise ValueError("Password must contain at least one special character")
    return password


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1, max_length=255)
    phone_number: str | None = None

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserInvite(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = None
    avatar_url: str | None = None
    preferences_json: dict | None = None


class UserAdminUpdate(BaseModel):
    status: str | None = None
    role_ids: list[uuid.UUID] | None = None
    is_superuser: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str
    status: str
    is_superuser: bool
    is_email_verified: bool
    mfa_enabled: bool
    avatar_url: str | None
    phone_number: str | None
    last_login_at: datetime | None
    created_at: datetime
    roles: list[RoleRead] = Field(default_factory=list)


class UserPublic(ORMBase):
    """Minimal user representation embedded in other resources (assignees, actors, etc.)."""

    id: uuid.UUID
    full_name: str
    email: EmailStr
    avatar_url: str | None


# --------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class APIKeyCreateResponse(ORMBase):
    id: uuid.UUID
    name: str
    raw_key: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None


class APIKeyRead(ORMBase):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime