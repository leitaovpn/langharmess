"""SQLite-backed session index plugin."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides

from langharmess_core.common.ids import validate_id
from langharmess_core.contracts import SessionIndexProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    turns INTEGER NOT NULL DEFAULT 0,
    last_agent_id TEXT NOT NULL DEFAULT '',
    agents_used TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (user_id, session_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "turns": row["turns"],
        "last_agent_id": row["last_agent_id"],
        "agents_used": json.loads(row["agents_used"]),
    }


@ComponentFactory("session-index-plugin-factory")
@Provides(SessionIndexProvider)
@Property("_plugin_name", "plugin.name", "sqlite-session-index")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_path", "plugin.sessions.path", "langharmess_sessions.sqlite3")
class SQLiteSessionIndexPlugin:
    """Tracks per-user sessions and which agents each session has used."""

    def __init__(self) -> None:
        self._plugin_name = "sqlite-session-index"
        self._plugin_version = "1.0.0"
        self._path = "langharmess_sessions.sqlite3"
        self._connection: aiosqlite.Connection | None = None

    async def new_session(self, user_id: str) -> str:
        user = validate_id(user_id, field="user_id")
        session_id = uuid4().hex
        timestamp = _now()
        connection = await self._ensure_connection()
        await connection.execute(
            "INSERT INTO sessions (user_id, session_id, created_at, last_used_at,"
            " turns, last_agent_id, agents_used) VALUES (?, ?, ?, ?, 0, '', '[]')",
            (user, session_id, timestamp, timestamp),
        )
        await connection.commit()
        return session_id

    async def touch(self, user_id: str, session_id: str, agent_id: str) -> None:
        user = validate_id(user_id, field="user_id")
        session = validate_id(session_id, field="session_id")
        agent = validate_id(agent_id, field="agent_id")
        timestamp = _now()
        connection = await self._ensure_connection()
        record = await self.get_session(user, session)
        if record is None:
            await connection.execute(
                "INSERT INTO sessions (user_id, session_id, created_at, last_used_at,"
                " turns, last_agent_id, agents_used) VALUES (?, ?, ?, ?, 1, ?, ?)",
                (user, session, timestamp, timestamp, agent, json.dumps([agent])),
            )
        else:
            agents = list(record["agents_used"])
            if agent not in agents:
                agents.append(agent)
            await connection.execute(
                "UPDATE sessions SET last_used_at = ?, turns = turns + 1,"
                " last_agent_id = ?, agents_used = ?"
                " WHERE user_id = ? AND session_id = ?",
                (timestamp, agent, json.dumps(agents), user, session),
            )
        await connection.commit()

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        user = validate_id(user_id, field="user_id")
        session = validate_id(session_id, field="session_id")
        connection = await self._ensure_connection()
        async with connection.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND session_id = ?",
            (user, session),
        ) as cursor:
            row = await cursor.fetchone()
        return _record(row) if row is not None else None

    async def list_sessions(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        user = validate_id(user_id, field="user_id")
        connection = await self._ensure_connection()
        async with connection.execute(
            "SELECT * FROM sessions WHERE user_id = ?"
            " ORDER BY last_used_at DESC, rowid DESC LIMIT ?",
            (user, max(0, limit)),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_record(row) for row in rows]

    async def _ensure_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            path = Path(self._path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(path)
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.executescript(_SCHEMA)
            await connection.commit()
            self._connection = connection
        return self._connection

    @Invalidate
    def _invalidate(self, bundle_context: Any) -> None:
        if self._connection is None:
            return
        connection = self._connection
        self._connection = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(connection.close())
        else:
            loop.create_task(connection.close())

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
