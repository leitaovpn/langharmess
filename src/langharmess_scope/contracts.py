"""Storage and query contracts for generic scopes."""

from __future__ import annotations

from typing import Protocol

from langharmess_scope.model import Scope, ScopeId, ScopeSnapshot


class ScopeStore(Protocol):
    """Persists complete snapshots without imposing a storage technology."""

    def load(self) -> ScopeSnapshot | None: ...

    def save(self, snapshot: ScopeSnapshot, *, expected_version: int) -> int: ...


class ScopeTreeProvider(Protocol):
    """Read interface consumed by systems that apply their own scope policy."""

    def get(self, scope_id: ScopeId) -> Scope | None: ...

    def require(self, scope_id: ScopeId) -> Scope: ...

    def ancestors(
        self, scope_id: ScopeId, *, include_self: bool = False
    ) -> tuple[Scope, ...]: ...

    def depth(self, scope_id: ScopeId) -> int: ...

    def is_ancestor(
        self,
        ancestor_id: ScopeId,
        descendant_id: ScopeId,
        *,
        include_self: bool = False,
    ) -> bool: ...

