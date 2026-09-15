"""Unit tests for the generic, persistent scope tree."""

from __future__ import annotations

import pytest

from langharmess_scope import (
    ROOT_SCOPE_ID,
    InMemoryScopeStore,
    ScopeConflictError,
    ScopeId,
    ScopeNotEmptyError,
    ScopeNotFoundError,
    ScopeTree,
)


def test_tree_starts_with_a_persisted_root() -> None:
    store = InMemoryScopeStore()
    tree = ScopeTree(store)

    assert tree.require(ROOT_SCOPE_ID).parent_id is None
    assert tree.depth(ROOT_SCOPE_ID) == 0
    assert store.load() is not None


def test_create_and_query_a_scope_hierarchy() -> None:
    tree = ScopeTree()
    organization = tree.create(ScopeId("org"), "Organization")
    agent = tree.create(ScopeId("agent"), "Agent", organization.id)
    session = tree.create(ScopeId("session"), "Session", agent.id)

    assert tree.parent(session.id) == agent
    assert tree.children(organization.id) == (agent,)
    assert tree.ancestors(session.id) == (agent, organization, tree.require(ROOT_SCOPE_ID))
    assert tree.ancestors(session.id, include_self=True)[0] == session
    assert tree.descendants(organization.id) == (agent, session)
    assert tree.depth(session.id) == 3
    assert tree.is_ancestor(organization.id, session.id)
    assert not tree.is_ancestor(session.id, organization.id)


def test_scope_ids_are_unique_and_parents_must_exist() -> None:
    tree = ScopeTree()
    tree.create(ScopeId("agent"), "Agent")

    with pytest.raises(ScopeConflictError):
        tree.create(ScopeId("agent"), "Duplicate")
    with pytest.raises(ScopeNotFoundError):
        tree.create(ScopeId("orphan"), "Orphan", ScopeId("missing"))
    with pytest.raises(ValueError, match="non-empty"):
        tree.create(ScopeId(""), "Empty")


def test_remove_requires_recursive_for_non_empty_scope() -> None:
    tree = ScopeTree()
    tree.create(ScopeId("agent"), "Agent")
    tree.create(ScopeId("session"), "Session", ScopeId("agent"))

    with pytest.raises(ScopeNotEmptyError):
        tree.remove(ScopeId("agent"))

    assert tree.remove(ScopeId("agent"), recursive=True) == (
        ScopeId("session"),
        ScopeId("agent"),
    )
    assert tree.get(ScopeId("agent")) is None
    with pytest.raises(ValueError, match="root"):
        tree.remove(ROOT_SCOPE_ID, recursive=True)


def test_tree_restores_from_store_and_detects_stale_writes() -> None:
    store = InMemoryScopeStore()
    first = ScopeTree(store)
    second = ScopeTree(store)
    first.create(ScopeId("agent"), "Agent")

    with pytest.raises(ScopeConflictError, match="version"):
        second.create(ScopeId("other"), "Other")

    restored = ScopeTree(store)
    assert restored.require(ScopeId("agent")).name == "Agent"

