"""PluginManager seeds the fixed scope topology on start."""

from __future__ import annotations

import pytest

from langharness_plugin.plugin_manager import PluginManager
from langharness_plugin.registry import PluginRegistry
from langharness_plugin.scope_const import (
    AGENT_SCOPE_ID,
    ROOT_SCOPE_ID,
    SERVER_SCOPE_ID,
    UI_SCOPE_ID,
)
from langharness_scope import ScopeId, ScopeTree


def test_start_seeds_builtin_scopes() -> None:
    manager = PluginManager(PluginRegistry([]))
    manager.start()
    try:
        tree = manager.scope_tree
        assert {scope.id for scope in tree.snapshot().scopes} == {
            ROOT_SCOPE_ID,
            UI_SCOPE_ID,
            SERVER_SCOPE_ID,
            AGENT_SCOPE_ID,
        }
        agent = tree.get(AGENT_SCOPE_ID)
        assert agent is not None
        assert agent.parent_id == ROOT_SCOPE_ID
        server = tree.get(SERVER_SCOPE_ID)
        assert server is not None
        assert server.parent_id == ROOT_SCOPE_ID
        ui = tree.get(UI_SCOPE_ID)
        assert ui is not None
        assert ui.parent_id == ROOT_SCOPE_ID
    finally:
        manager.stop()


def test_seeding_is_idempotent_across_restarts() -> None:
    manager = PluginManager(PluginRegistry([]))
    manager.start()
    manager.stop()
    manager.start()
    try:
        tree = manager.scope_tree
        assert len(tree.snapshot().scopes) == 4
        agent = tree.get(AGENT_SCOPE_ID)
        assert agent is not None
        assert agent.parent_id == ROOT_SCOPE_ID
        server = tree.get(SERVER_SCOPE_ID)
        assert server is not None
        assert server.parent_id == ROOT_SCOPE_ID
        ui = tree.get(UI_SCOPE_ID)
        assert ui is not None
        assert ui.parent_id == ROOT_SCOPE_ID
    finally:
        manager.stop()


def test_seeding_rejects_a_scope_with_a_conflicting_parent() -> None:
    tree = ScopeTree()
    custom = tree.create(ScopeId("custom"), "Custom")
    tree.create(AGENT_SCOPE_ID, "Agent", custom.id)
    manager = PluginManager(PluginRegistry([]), scope_tree=tree)
    with pytest.raises(ValueError, match="already has a different parent"):
        manager.start()
    assert not manager.started
    tree.remove(ScopeId("custom"), recursive=True)
    try:
        manager.start()
        assert manager.started
    finally:
        manager.stop()
