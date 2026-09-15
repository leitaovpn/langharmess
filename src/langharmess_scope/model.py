"""Value objects used by the generic scope hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

ScopeId = NewType("ScopeId", str)
ROOT_SCOPE_ID = ScopeId("root")


@dataclass(frozen=True, slots=True)
class Scope:
    """One immutable node in a scope tree."""

    id: ScopeId
    parent_id: ScopeId | None
    name: str


@dataclass(frozen=True, slots=True)
class ScopeSnapshot:
    """A persistence-neutral, versioned snapshot of a complete scope tree."""

    version: int
    scopes: tuple[Scope, ...]

