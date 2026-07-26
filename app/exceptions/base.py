from __future__ import annotations
from typing import Any


class AppException(Exception):
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    status_code = 404
    error_code = "not_found"


class AlreadyExistsError(AppException):
    status_code = 409
    error_code = "already_exists"


class ValidationError(AppException):
    status_code = 422
    error_code = "validation_error"


class AuthenticationError(AppException):
    status_code = 401
    error_code = "authentication_failed"


class InvalidCredentialsError(AuthenticationError):
    error_code = "invalid_credentials"


class TokenExpiredError(AuthenticationError):
    error_code = "token_expired"


class TokenInvalidError(AuthenticationError):
    error_code = "token_invalid"


class MFARequiredError(AuthenticationError):
    error_code = "mfa_required"
    status_code = 401


class AuthorizationError(AppException):
    status_code = 403
    error_code = "forbidden"


class InsufficientPermissionsError(AuthorizationError):
    error_code = "insufficient_permission"


class RateLimitExceededError(AppException):
    status_code = 429
    error_code = "rate_limit_exceeded"


class ConflictError(AppException):
    status_code = 409
    error_code = "conflict"


class ExternalServiceError(AppException):
    status_code = 502
    error_code = "external_service_error"


class ConnectorError(ExternalServiceError):
    error_code = "connector_error"


class CacheError(AppException):
    status_code = 500
    error_code = "cache_error"


class DatabaseError(AppException):
    status_code = 500
    error_code = "database_error"


class BadRequestError(AppException):
    status_code = 400
    error_code = "bad_request"


class FileStorageError(AppException):
    error_code = "file_storage_error"
    status_code = 500


class AIServiceError(ExternalServiceError):
    error_code = "ai_service_error"

# external