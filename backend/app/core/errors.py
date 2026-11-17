"""Domain exceptions mapped to the API error envelope (docs/API_SPEC.md §1.3)."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    retryable = False

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message or self.__class__.__doc__ or self.code)
        self.message = message or (self.__class__.__doc__ or self.code).strip()
        self.details = details or {}
        if code:
            self.code = code


class BadRequest(AppError):
    """The request is invalid."""


class UnsafeUrl(AppError):
    """The URL is not allowed."""

    code = "unsafe_url"


class Unauthorized(AppError):
    """Authentication required."""

    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    """This account is not allowed to use this deployment."""

    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    """Resource not found."""

    status_code = 404
    code = "not_found"


class Conflict(AppError):
    """The request conflicts with the current state."""

    status_code = 409
    code = "conflict"


class Duplicate(Conflict):
    """This item already exists."""

    code = "duplicate"


class InvalidStateTransition(Conflict):
    """That status change is not allowed."""

    code = "invalid_state_transition"


class IdempotencyConflict(Conflict):
    """Idempotency key reused with a different request."""

    code = "idempotency_conflict"


class FileTooLarge(AppError):
    """The file is too large."""

    status_code = 413
    code = "file_too_large"


class UnsupportedFileType(AppError):
    """Only PDF and DOCX files are supported."""

    status_code = 415
    code = "unsupported_file_type"


class ValidationFailed(AppError):
    """Validation failed."""

    status_code = 422
    code = "validation_error"


class SourceNotPermitted(AppError):
    """This source cannot be fetched."""

    status_code = 422
    code = "source_not_permitted"


class ApprovalRequired(AppError):
    """Explicit approval is required for this action."""

    status_code = 422
    code = "approval_required"


class ApprovalMismatch(AppError):
    """The approved payload no longer matches what would be executed."""

    status_code = 422
    code = "approval_mismatch"


class ApprovalExpired(AppError):
    """The approval has expired."""

    status_code = 422
    code = "approval_expired"


class IntegrationNotConnected(AppError):
    """The required integration is not connected."""

    status_code = 422
    code = "integration_not_connected"


class UnverifiedRecipient(AppError):
    """The recipient email is not a verified public address."""

    status_code = 422
    code = "unverified_recipient"


class RateLimited(AppError):
    """Too many requests."""

    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int, message: str | None = None):
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after


class LLMQuotaExhausted(AppError):
    """Daily LLM budget reached; work is queued until the next window."""

    status_code = 429
    code = "llm_quota_exhausted"


class FetchFailed(AppError):
    """Fetching the URL failed."""

    status_code = 502
    code = "fetch_failed"
    retryable = True


class UpstreamError(AppError):
    """An upstream provider returned an error."""

    status_code = 502
    code = "upstream_error"
    retryable = True


class LLMUnavailable(AppError):
    """The LLM provider is unavailable."""

    status_code = 503
    code = "llm_unavailable"
    retryable = True


class InvalidLLMOutput(AppError):
    """The model returned output that failed validation."""

    status_code = 502
    code = "invalid_llm_output"


def error_body(code: str, message: str, details: dict[str, Any] | None, request_id: str | None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}, "request_id": request_id}}
