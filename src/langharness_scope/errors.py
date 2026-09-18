"""Scope hierarchy errors."""


class ScopeError(Exception):
    """Base error for scope operations."""


class ScopeNotFoundError(ScopeError, KeyError):
    """Raised when a requested scope does not exist."""


class ScopeConflictError(ScopeError, ValueError):
    """Raised for duplicate scopes or optimistic-write conflicts."""


class ScopeNotEmptyError(ScopeError, ValueError):
    """Raised when non-recursive removal targets a parent scope."""

