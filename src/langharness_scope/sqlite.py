"""SQLite-backed implementation of the scope snapshot store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from langharness_scope.errors import ScopeConflictError
from langharness_scope.model import Scope, ScopeId, ScopeSnapshot


class SqliteScopeStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scope_state ("
                "singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1), "
                "version INTEGER NOT NULL, snapshot_json TEXT NOT NULL)"
            )

    def load(self) -> ScopeSnapshot | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT version, snapshot_json FROM scope_state WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(row[1])
        scopes = tuple(
            Scope(
                ScopeId(item["id"]),
                ScopeId(item["parent_id"]) if item["parent_id"] is not None else None,
                item["name"],
            )
            for item in raw
        )
        return ScopeSnapshot(int(row[0]), scopes)

    def save(self, snapshot: ScopeSnapshot, *, expected_version: int) -> int:
        payload = json.dumps(
            [
                {
                    "id": scope.id,
                    "parent_id": scope.parent_id,
                    "name": scope.name,
                }
                for scope in snapshot.scopes
            ]
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM scope_state WHERE singleton_id = 1"
            ).fetchone()
            current = int(row[0]) if row is not None else 0
            if current != expected_version:
                raise ScopeConflictError(
                    f"Scope store version changed: expected {expected_version}, got {current}"
                )
            version = current + 1
            connection.execute(
                "INSERT INTO scope_state VALUES (1, ?, ?) "
                "ON CONFLICT(singleton_id) DO UPDATE SET "
                "version=excluded.version, snapshot_json=excluded.snapshot_json",
                (version, payload),
            )
        return version

