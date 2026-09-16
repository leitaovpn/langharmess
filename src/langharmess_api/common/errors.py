"""Unified HTTP error construction for API routes."""

from __future__ import annotations

from fastapi import HTTPException


def http_error(
    status_code: int,
    message: str,
    *,
    code: str = "API_ERROR",
    error_type: str = "APIError",
) -> HTTPException:
    """Build an HTTPException with a stable error code and type header."""
    return HTTPException(
        status_code=status_code,
        detail=message,
        headers={"X-Error-Code": code, "X-Error-Type": error_type},
    )


def operation_error(
    exc: Exception,
    *,
    status_code: int = 400,
    code: str | None = None,
) -> HTTPException:
    """Wrap a plugin operation exception with its concrete type."""
    if code is None:
        code = _operation_code(exc)
    return http_error(
        status_code,
        str(exc),
        code=code,
        error_type=type(exc).__name__,
    )


def _operation_code(exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return "PLUGIN_NOT_FOUND"
    if isinstance(exc, ValueError):
        return "PLUGIN_VALIDATION_ERROR"
    if isinstance(exc, RuntimeError):
        return "PLUGIN_RUNTIME_ERROR"
    return "PLUGIN_OPERATION_FAILED"
