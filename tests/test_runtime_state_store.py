"""SQLite persistence for scopes and dynamic plugin registrations."""

from pathlib import Path

import pytest

from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.state_store import (
    InMemoryRuntimeStateStore,
    PersistedPluginRegistration,
    PluginStateConflictError,
    PluginStateSnapshot,
    RuntimeStateSnapshot,
    SqlitePluginStateStore,
    SqliteRuntimeStateStore,
)
from langharmess_scope import Scope, ScopeConflictError, ScopeId, ScopeSnapshot
from langharmess_scope.sqlite import SqliteScopeStore


def plugin_snapshot(version: int = 0) -> PluginStateSnapshot:
    descriptor = PluginDescriptor(
        name="dynamic",
        version="1",
        module="dynamic.module",
        factory="dynamic-factory",
        instance="dynamic",
        specification="dynamic.service",
        scope="server",
        scope_parent="root",
    )
    return PluginStateSnapshot(
        version,
        (
            PersistedPluginRegistration(
                package_id="example.package",
                contribution_id="dynamic",
                package_version="1",
                scope_id=ScopeId("server"),
                plugin_key="dynamic",
                descriptor=descriptor,
                enabled=True,
                status="installed",
            ),
        ),
    )


def runtime_snapshot(version: int = 0) -> RuntimeStateSnapshot:
    plugin = plugin_snapshot().registrations[0]
    return RuntimeStateSnapshot(
        version,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "server", "parent_id": "root", "name": "server"},
        ),
        (plugin,),
    )


def test_sqlite_scope_store_round_trip_and_optimistic_conflict(tmp_path: Path) -> None:
    store = SqliteScopeStore(tmp_path / "runtime.sqlite3")
    snapshot = ScopeSnapshot(
        0,
        (
            Scope(ScopeId("root"), None, "root"),
            Scope(ScopeId("server"), ScopeId("root"), "Server"),
        ),
    )
    version = store.save(snapshot, expected_version=0)
    assert version == 1
    assert store.load() == ScopeSnapshot(1, snapshot.scopes)
    with pytest.raises(ScopeConflictError):
        store.save(snapshot, expected_version=0)


def test_sqlite_plugin_store_round_trip_and_optimistic_conflict(
    tmp_path: Path,
) -> None:
    store = SqlitePluginStateStore(tmp_path / "runtime.sqlite3")
    snapshot = plugin_snapshot()
    version = store.save(snapshot, expected_version=0)
    assert version == 1
    assert store.load() == PluginStateSnapshot(1, snapshot.registrations)
    with pytest.raises(PluginStateConflictError):
        store.save(snapshot, expected_version=0)


def test_sqlite_runtime_store_round_trip_and_conflict(tmp_path: Path) -> None:
    store = SqliteRuntimeStateStore(tmp_path / "runtime.sqlite3")
    snapshot = runtime_snapshot()
    version = store.save(snapshot, expected_version=0)
    assert version == 1
    assert store.load() == RuntimeStateSnapshot(1, snapshot.scopes, snapshot.plugins)
    with pytest.raises(PluginStateConflictError):
        store.save(snapshot, expected_version=0)


def test_in_memory_runtime_store_conflict_and_empty_load() -> None:
    store = InMemoryRuntimeStateStore()
    assert store.load() is None
    snapshot = runtime_snapshot()
    assert store.save(snapshot, expected_version=0) == 1
    with pytest.raises(PluginStateConflictError):
        store.save(snapshot, expected_version=0)
