"""Persistent declarations of dynamically registered plugins."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from langharness_plugin.registry import PluginDescriptor
from langharness_scope import ScopeId

PluginStatus = Literal[
    "installed", "disabled", "upgrade_available", "missing", "failed"
]


class PluginStateConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PersistedPluginRegistration:
    package_id: str
    contribution_id: str
    package_version: str
    scope_id: ScopeId
    plugin_key: str
    descriptor: PluginDescriptor
    enabled: bool
    status: PluginStatus


@dataclass(frozen=True, slots=True)
class PluginStateSnapshot:
    version: int
    registrations: tuple[PersistedPluginRegistration, ...]


class PluginStateStore(Protocol):
    def load(self) -> PluginStateSnapshot | None: ...

    def save(
        self, snapshot: PluginStateSnapshot, *, expected_version: int
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class RuntimeStateSnapshot:
    version: int
    scopes: tuple[dict[str, str | None], ...]
    plugins: tuple[PersistedPluginRegistration, ...]


class RuntimeStateStore(Protocol):
    def load(self) -> RuntimeStateSnapshot | None: ...

    def save(
        self, snapshot: RuntimeStateSnapshot, *, expected_version: int
    ) -> int: ...


class InMemoryRuntimeStateStore:
    def __init__(self) -> None:
        self.snapshot: RuntimeStateSnapshot | None = None

    def load(self) -> RuntimeStateSnapshot | None:
        return self.snapshot

    def save(self, snapshot: RuntimeStateSnapshot, *, expected_version: int) -> int:
        current = self.snapshot.version if self.snapshot is not None else 0
        if current != expected_version:
            raise PluginStateConflictError(
                f"Runtime state version changed: expected {expected_version}, got {current}"
            )
        version = current + 1
        self.snapshot = replace(snapshot, version=version)
        return version


class SqliteRuntimeStateStore:
    """Atomically persists the scope tree and plugin registrations once."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_state ("
                "singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1), "
                "version INTEGER NOT NULL, snapshot_json TEXT NOT NULL)"
            )

    def load(self) -> RuntimeStateSnapshot | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT version, snapshot_json FROM runtime_state WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(row[1])
        return RuntimeStateSnapshot(
            int(row[0]),
            tuple(raw["scopes"]),
            tuple(SqlitePluginStateStore._decode(item) for item in raw["plugins"]),
        )

    def save(self, snapshot: RuntimeStateSnapshot, *, expected_version: int) -> int:
        payload = json.dumps(
            {
                "scopes": list(snapshot.scopes),
                "plugins": [
                    SqlitePluginStateStore._encode(item) for item in snapshot.plugins
                ],
            }
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM runtime_state WHERE singleton_id = 1"
            ).fetchone()
            current = int(row[0]) if row is not None else 0
            if current != expected_version:
                raise PluginStateConflictError(
                    f"Runtime state version changed: expected {expected_version}, got {current}"
                )
            version = current + 1
            connection.execute(
                "INSERT INTO runtime_state VALUES (1, ?, ?) "
                "ON CONFLICT(singleton_id) DO UPDATE SET "
                "version=excluded.version, snapshot_json=excluded.snapshot_json",
                (version, payload),
            )
        return version


class SqlitePluginStateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS plugin_state ("
                "singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1), "
                "version INTEGER NOT NULL, snapshot_json TEXT NOT NULL)"
            )

    def load(self) -> PluginStateSnapshot | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT version, snapshot_json FROM plugin_state WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            return None
        registrations = tuple(self._decode(item) for item in json.loads(row[1]))
        return PluginStateSnapshot(int(row[0]), registrations)

    def save(self, snapshot: PluginStateSnapshot, *, expected_version: int) -> int:
        payload = json.dumps([self._encode(item) for item in snapshot.registrations])
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM plugin_state WHERE singleton_id = 1"
            ).fetchone()
            current = int(row[0]) if row is not None else 0
            if current != expected_version:
                raise PluginStateConflictError(
                    f"Plugin state version changed: expected {expected_version}, got {current}"
                )
            version = current + 1
            connection.execute(
                "INSERT INTO plugin_state VALUES (1, ?, ?) "
                "ON CONFLICT(singleton_id) DO UPDATE SET "
                "version=excluded.version, snapshot_json=excluded.snapshot_json",
                (version, payload),
            )
        return version

    @staticmethod
    def _encode(item: PersistedPluginRegistration) -> dict[str, object]:
        return {
            "package_id": item.package_id,
            "contribution_id": item.contribution_id,
            "package_version": item.package_version,
            "scope_id": item.scope_id,
            "plugin_key": item.plugin_key,
            "descriptor": item.descriptor.to_dict(),
            "enabled": item.enabled,
            "status": item.status,
        }

    @staticmethod
    def _decode(data: dict[str, object]) -> PersistedPluginRegistration:
        descriptor_data = data["descriptor"]
        if not isinstance(descriptor_data, dict):
            raise ValueError("Invalid persisted plugin descriptor")
        return PersistedPluginRegistration(
            package_id=str(data["package_id"]),
            contribution_id=str(data["contribution_id"]),
            package_version=str(data["package_version"]),
            scope_id=ScopeId(str(data["scope_id"])),
            plugin_key=str(data["plugin_key"]),
            descriptor=PluginDescriptor.from_dict(descriptor_data),
            enabled=bool(data["enabled"]),
            status=str(data["status"]),  # type: ignore[arg-type]
        )
