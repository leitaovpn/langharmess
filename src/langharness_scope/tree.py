"""Thread-safe in-memory scope tree with pluggable snapshot persistence."""

from __future__ import annotations

from threading import RLock

from langharness_scope.contracts import ScopeStore
from langharness_scope.errors import (
    ScopeConflictError,
    ScopeNotEmptyError,
    ScopeNotFoundError,
)
from langharness_scope.model import ROOT_SCOPE_ID, Scope, ScopeId, ScopeSnapshot


class InMemoryScopeStore:
    """In-process store useful as the default and for isolated tests."""

    def __init__(self) -> None:
        self._snapshot: ScopeSnapshot | None = None
        self._lock = RLock()

    def load(self) -> ScopeSnapshot | None:
        with self._lock:
            return self._snapshot

    def save(self, snapshot: ScopeSnapshot, *, expected_version: int) -> int:
        with self._lock:
            current = self._snapshot.version if self._snapshot is not None else 0
            if current != expected_version:
                raise ScopeConflictError(
                    f"Scope store version changed: expected {expected_version}, got {current}"
                )
            version = current + 1
            self._snapshot = ScopeSnapshot(version, tuple(snapshot.scopes))
            return version


class ScopeTree:
    """Mutable tree whose persistence boundary is an immutable snapshot."""

    def __init__(self, store: ScopeStore | None = None) -> None:
        self._store = store if store is not None else InMemoryScopeStore()
        self._lock = RLock()
        snapshot = self._store.load()
        if snapshot is None:
            root = Scope(ROOT_SCOPE_ID, None, "root")
            self._scopes = {ROOT_SCOPE_ID: root}
            self._version = self._store.save(
                ScopeSnapshot(0, (root,)), expected_version=0
            )
        else:
            self._scopes = {scope.id: scope for scope in snapshot.scopes}
            self._version = snapshot.version
            self._validate_snapshot()

    def get(self, scope_id: ScopeId) -> Scope | None:
        with self._lock:
            return self._scopes.get(scope_id)

    def snapshot(self) -> ScopeSnapshot:
        with self._lock:
            return ScopeSnapshot(self._version, tuple(self._scopes.values()))

    def require(self, scope_id: ScopeId) -> Scope:
        scope = self.get(scope_id)
        if scope is None:
            raise ScopeNotFoundError(scope_id)
        return scope

    def create(
        self,
        scope_id: ScopeId,
        name: str,
        parent_id: ScopeId = ROOT_SCOPE_ID,
    ) -> Scope:
        if not str(scope_id).strip() or not name.strip():
            raise ValueError("Scope id and name must be non-empty")
        with self._lock:
            if scope_id in self._scopes:
                raise ScopeConflictError(f"Scope already exists: {scope_id}")
            if parent_id not in self._scopes:
                raise ScopeNotFoundError(parent_id)
            scope = Scope(scope_id, parent_id, name)
            updated = {**self._scopes, scope_id: scope}
            self._commit(updated)
            return scope

    def parent(self, scope_id: ScopeId) -> Scope | None:
        scope = self.require(scope_id)
        return self.require(scope.parent_id) if scope.parent_id is not None else None

    def children(self, scope_id: ScopeId) -> tuple[Scope, ...]:
        self.require(scope_id)
        with self._lock:
            return tuple(
                scope for scope in self._scopes.values() if scope.parent_id == scope_id
            )

    def ancestors(
        self, scope_id: ScopeId, *, include_self: bool = False
    ) -> tuple[Scope, ...]:
        current = self.require(scope_id)
        result: list[Scope] = [current] if include_self else []
        while current.parent_id is not None:
            current = self.require(current.parent_id)
            result.append(current)
        return tuple(result)

    def descendants(
        self, scope_id: ScopeId, *, include_self: bool = False
    ) -> tuple[Scope, ...]:
        root = self.require(scope_id)
        result: list[Scope] = [root] if include_self else []

        def visit(parent_id: ScopeId) -> None:
            for child in self.children(parent_id):
                result.append(child)
                visit(child.id)

        visit(scope_id)
        return tuple(result)

    def depth(self, scope_id: ScopeId) -> int:
        return len(self.ancestors(scope_id))

    def is_ancestor(
        self,
        ancestor_id: ScopeId,
        descendant_id: ScopeId,
        *,
        include_self: bool = False,
    ) -> bool:
        self.require(ancestor_id)
        return any(
            scope.id == ancestor_id
            for scope in self.ancestors(descendant_id, include_self=include_self)
        )

    def remove(
        self, scope_id: ScopeId, *, recursive: bool = False
    ) -> tuple[ScopeId, ...]:
        if scope_id == ROOT_SCOPE_ID:
            raise ValueError("The root scope cannot be removed")
        self.require(scope_id)
        descendants = self.descendants(scope_id)
        if descendants and not recursive:
            raise ScopeNotEmptyError(f"Scope has children: {scope_id}")
        removed = tuple(scope.id for scope in reversed(descendants)) + (scope_id,)
        with self._lock:
            updated = {
                key: value for key, value in self._scopes.items() if key not in removed
            }
            self._commit(updated)
        return removed

    def _commit(self, scopes: dict[ScopeId, Scope]) -> None:
        snapshot = ScopeSnapshot(self._version, tuple(scopes.values()))
        version = self._store.save(snapshot, expected_version=self._version)
        self._scopes = scopes
        self._version = version

    def _validate_snapshot(self) -> None:
        root = self._scopes.get(ROOT_SCOPE_ID)
        if root is None or root.parent_id is not None:
            raise ValueError("Scope snapshot must contain a root")
        for scope in self._scopes.values():
            if scope.id != ROOT_SCOPE_ID and scope.parent_id not in self._scopes:
                raise ValueError(f"Scope snapshot has an orphan: {scope.id}")
            seen: set[ScopeId] = set()
            current = scope
            while current.parent_id is not None:
                if current.id in seen:
                    raise ValueError(f"Scope snapshot contains a cycle: {scope.id}")
                seen.add(current.id)
                current = self._scopes[current.parent_id]
