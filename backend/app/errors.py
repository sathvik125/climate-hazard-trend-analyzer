"""Application errors and the handlers that turn them into safe JSON responses.

Every error body has the same shape:
    {"error": {"code": "...", "message": "...", "details": ...}}
Stack traces and configuration values are logged server-side and never returned.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: Any = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class InvalidRequestError(AppError):
    status_code = 422
    code = "invalid_request"


class InsufficientDataError(AppError):
    """The source data cannot support the requested analysis."""

    status_code = 422
    code = "insufficient_data"


class RateLimitExceededError(AppError):
    status_code = 429
    code = "rate_limited"


class UpstreamUnavailableError(AppError):
    status_code = 502
    code = "upstream_unavailable"


class UpstreamInvalidDataError(AppError):
    status_code = 502
    code = "upstream_invalid_data"


class UpstreamRateLimitedError(AppError):
    status_code = 503
    code = "upstream_rate_limited"


class UpstreamTimeoutError(AppError):
    status_code = 504
    code = "upstream_timeout"


class StorageError(AppError):
    status_code = 503
    code = "database_unavailable"


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", []) if part != "query"),
                "message": str(err.get("msg", "invalid value")).removeprefix("Value error, "),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_body("invalid_request", "One or more request parameters are invalid.", details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "An unexpected error occurred."),
        )
