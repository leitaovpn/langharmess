"""Unit tests for PluginManager start, discovery, and scope APIs."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from unittest.mock import Mock

import pytest

from langharness_plugin.errors import ScopeHasChildrenError, ScopeHasInstancesError
from langharness_plugin.plugin_manager import PluginManager
from langharness_plugin.registry import PluginRegistry, plugin_metadata
from langharness_scope import ROOT_SCOPE_ID, ScopeId

DESCRIPTION = (
    "Test plugin. Implements test.spec. Use in unit tests only. "
    "No properties. Uninstall when tests finish."
)


class EntryPoint:
    def __init__(self, target, name: str = "dynamic") -> None:
        self.target = target
        self.name = name
        self.value = f"{name}:load"

    def load(self):
        return self.target


@plugin_metadata(
    name="echo",
    version="1.0.0",
    factory="echo-factory",
    specification="test.echo",
    description=DESCRIPTION,
)
class Echo:
    pass


def manager_with(entry_points=()) -> PluginManager:
    manager = PluginManager(
        PluginRegistry(),
        discovery=lambda: [EntryPoint(item, f"ep-{i}") for i, item in enumerate(entry_points)],
    )
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    return manager


class TestLifecycle:
    def test_not_started_errors_and_stop_is_noop(self) -> None:
        manager = PluginManager(PluginRegistry())
        assert manager.started is False
        manager.stop()
        with pytest.raises(RuntimeError, match="not started"):
            manager.discover()

    def test_start_twice_raises(self) -> None:
        manager = PluginManager(PluginRegistry())
        manager._framework = Mock()
        with pytest.raises(RuntimeError, match="already started"):
            manager.start()


class TestDiscovery:
    def test_discover_builds_catalog_without_installing(self) -> None:
        manager = manager_with([Echo])
        snapshot = manager.discover()
        assert len(snapshot.descriptors) == 1
        assert snapshot.descriptors[0].factory == "echo-factory"
        assert manager._discovered == {
            (Echo.__module__, "echo-factory"): snapshot.descriptors[0]
        }
        manager._context.install_bundle.assert_not_called()

    def test_rediscover_replaces_catalog(self) -> None:
        manager = manager_with([Echo])
        manager.discover()
        manager.discover()
        assert len(manager._discovered) == 1

    def test_discovery_warnings_surface_in_snapshot(self) -> None:
        manager = manager_with([42])
        snapshot = manager.discover()
        assert snapshot.descriptors == ()
        assert snapshot.warnings


class TestScopes:
    def test_builtin_scopes_are_seeded_on_real_start(self) -> None:
        manager = PluginManager(PluginRegistry())
        manager.start()
        try:
            scopes = manager.list_scope()
            assert {scope.id for scope in scopes} >= {
                ROOT_SCOPE_ID,
                ScopeId("ui"),
                ScopeId("server"),
                ScopeId("agent"),
            }
        finally:
            manager.stop()

    def test_add_scope_requires_existing_parent(self) -> None:
        manager = manager_with()
        with pytest.raises(Exception):
            manager.add_scope(
                ScopeId("agent:a"), name="A", parent_id=ScopeId("missing")
            )
        manager.add_scope(ScopeId("agent"), name="Agent", parent_id=ROOT_SCOPE_ID)
        manager.add_scope(ScopeId("agent:a"), name="A", parent_id=ScopeId("agent"))
        assert manager.scope_tree.get(ScopeId("agent:a")) is not None

    def test_remove_scope_rejects_children_and_instances(self) -> None:
        manager = manager_with()
        manager.add_scope(ScopeId("agent"), name="Agent", parent_id=ROOT_SCOPE_ID)
        manager.add_scope(ScopeId("agent:a"), name="A", parent_id=ScopeId("agent"))
        with pytest.raises(ScopeHasChildrenError):
            manager.remove_scope(ScopeId("agent"))

        manager._instances["uuid-1"] = Mock(scope_id=ScopeId("agent:a"))
        manager._registration_instances[("m", "f", ScopeId("agent:a"))] = {"uuid-1"}
        with pytest.raises(ScopeHasInstancesError):
            manager.remove_scope(ScopeId("agent:a"))

    def test_remove_scope_recursive_deletes_instances(self) -> None:
        from langharness_plugin.registry import PluginInstanceSnapshot

        manager = manager_with()
        manager.add_scope(ScopeId("agent"), name="Agent", parent_id=ROOT_SCOPE_ID)
        manager.add_scope(ScopeId("agent:a"), name="A", parent_id=ScopeId("agent"))
        manager._instances["uuid-1"] = PluginInstanceSnapshot(
            "uuid-1", "f", "m", ScopeId("agent:a"), {}, True, 0, "active"
        )
        manager._ipopo.kill.return_value = None
        manager.remove_scope(ScopeId("agent:a"), recursive=True)
        assert manager._instances == {}
        manager._ipopo.kill.assert_called_once_with("uuid-1")
