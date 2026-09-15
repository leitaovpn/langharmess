"""Generic hierarchical scopes with pluggable persistence."""

from langharmess_scope.contracts import ScopeStore, ScopeTreeProvider
from langharmess_scope.errors import (
    ScopeConflictError,
    ScopeError,
    ScopeNotEmptyError,
    ScopeNotFoundError,
)
from langharmess_scope.model import ROOT_SCOPE_ID, Scope, ScopeId, ScopeSnapshot
from langharmess_scope.tree import InMemoryScopeStore, ScopeTree

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

