from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.exceptions.base import TokenExpiredError,TokenInvalidError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated = "auto")

class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    RESET_PASSWORD = "reset_password"
    EMAIL_VERIFY = " email_verify "
    MFA_CHALLENGE = " mfa_challenger"

def hash_password(plain_password:str) -> str :
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password : str) -> str :
    return pwd_context.verify(plain_password,hashed_password)

def encode(subject:str , token_type : TokenType, expires_delta : timedelta, extra_claims : dict[str, Any]|None = None) -> tuple[str,str]:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload: dict[str,Any] = {
        "sub" : subject,
        "type" : token_type.value,
        "iat" : now,
        "exp" : now + expires_delta,
        "iss" : settings.JWT_ISSUERS,
        "jti" : jti
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload,settings.SECRET_KEY, algorithm= settings.JWT_ALGORITHM)
    return token, jti

def create_access_token(subject:str, extra_claims : dict[str,Any] | None = None) ->  tuple[str,str]:
    return encode(subject,TokenType.ACCESS, timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES), extra_claims)

def create_refresh_token(subject :str) -> tuple[str,str]:
    return encode(subject,TokenType.REFRESH, timedelta(settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))

def create_special_token(subject :str, token_type : TokenType , expires_delta : timedelta) -> tuple[str,str] :
    return encode(subject,token_type,expires_delta)

def decode_token(token: str , expected_type : TokenType | None =None ) -> dict[str, Any] :
    try :
        payload = jwt.decode(token, settings.SECRET_KEY,algorithms=[settings.JWT_ALGORITHMT], issuer = settings.JWT_ISSUERS)
    except jwt.ExpiredSignatureError as exc :
        raise TokenExpiredError("Token has expired")  from exc
    except jwt.InvalidTokenError as exc :
        raise TokenInvalidError("Token is invalid") from exc 
    
    if expected_type and payload.get("type") != expected_type.value :
        raise TokenInvalidError(f"Expected token type '{expected_type}'")
    
    
    
#API Keys

def generate_api_key() -> tuple[str,str, str]:
    raw_secret = secrets.token_urlsafe(32)
    raw_key = f"{settings.API_KEY_PREFIX}{raw_secret}"
    key_hash = hash_api_key(raw_key)
    display_prefix = raw_key[: len(settings.API_KEY_PREFIX) + 8]
    return raw_key, key_hash, display_prefix
    
    
    
    
    
def hash_api_key(raw_key : str) -> str :
    return hashlib.sha256(f"{settings.SECRET_KEY}{raw_key}".encode())

def verify_api_key(raw_key : str, key_hash : str) -> bool :
    return secrets.compare_digest(hash_api_key(raw_key),key_hash)

def generate_secure_random_code(length : int = 6) -> str :
    return "" .join(secrets.choice("0123456789") for _ in range(length))