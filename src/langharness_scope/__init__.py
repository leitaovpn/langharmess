"""Generic hierarchical scopes with pluggable persistence."""

from langharness_scope.contracts import ScopeStore, ScopeTreeProvider
from langharness_scope.errors import (
    ScopeConflictError,
    ScopeError,
    ScopeNotEmptyError,
    ScopeNotFoundError,
)
from langharness_scope.model import ROOT_SCOPE_ID, Scope, ScopeId, ScopeSnapshot
from langharness_scope.tree import InMemoryScopeStore, ScopeTree

__all__ = [
    "ROOT_SCOPE_ID",
    "InMemoryScopeStore",
    "Scope",
    "ScopeConflictError",
    "ScopeError",
    "ScopeId",
    "ScopeNotEmptyError",
    "ScopeNotFoundError",
    "ScopeSnapshot",
    "ScopeStore",
    "ScopeTree",
    "ScopeTreeProvider",
]

