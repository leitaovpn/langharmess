"""Unit tests for the SQLite session index plugin."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from langharmess_core.plugins.sessions.sqlite import SQLiteSessionIndexPlugin


def make_plugin(tmp_path: Path) -> SQLiteSessionIndexPlugin:
    plugin = SQLiteSessionIndexPlugin()
    plugin._path = str(tmp_path / "sessions.sqlite3")
    return plugin


def test_new_session_creates_empty_record(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> tuple[str, dict[str, object] | None]:
        session_id = await plugin.new_session("local_user")
        return session_id, await plugin.get_session("local_user", session_id)

    session_id, record = asyncio.run(scenario())
    assert len(session_id) == 32
    assert record is not None
    assert record["user_id"] == "local_user"
    assert record["session_id"] == session_id
    assert record["turns"] == 0
    assert record["last_agent_id"] == ""
    assert record["agents_used"] == []


def test_get_session_returns_none_for_unknown(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    assert asyncio.run(plugin.get_session("local_user", "missing")) is None


def test_touch_creates_session_when_absent(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> dict[str, object] | None:
        await plugin.touch("local_user", "client-supplied", "simple_agent")
        return await plugin.get_session("local_user", "client-supplied")

    record = asyncio.run(scenario())
    assert record is not None
    assert record["turns"] == 1
    assert record["last_agent_id"] == "simple_agent"
    assert record["agents_used"] == ["simple_agent"]


def test_touch_accumulates_turns_and_agents(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> dict[str, object] | None:
        await plugin.touch("local_user", "s1", "simple_agent")
        await plugin.touch("local_user", "s1", "simple_agent")
        await plugin.touch("local_user", "s1", "other_agent")
        return await plugin.get_session("local_user", "s1")

    record = asyncio.run(scenario())
    assert record is not None
    assert record["turns"] == 3
    assert record["last_agent_id"] == "other_agent"
    assert record["agents_used"] == ["simple_agent", "other_agent"]


def test_list_sessions_orders_by_recent_use_per_user(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> list[dict[str, object]]:
        await plugin.touch("local_user", "old", "simple_agent")
        await plugin.touch("local_user", "new", "simple_agent")
        await plugin.touch("other_user", "foreign", "simple_agent")
        return await plugin.list_sessions("local_user")

    sessions = asyncio.run(scenario())
    assert [item["session_id"] for item in sessions] == ["new", "old"]
    assert all(item["user_id"] == "local_user" for item in sessions)


def test_list_sessions_respects_limit(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> list[dict[str, object]]:
        for index in range(3):
            await plugin.touch("local_user", f"s{index}", "simple_agent")
        return await plugin.list_sessions("local_user", limit=2)

    assert len(asyncio.run(scenario())) == 2


@pytest.mark.parametrize(
    ("user_id", "session_id", "agent_id"),
    [
        ("bad user", "s1", "simple_agent"),
        ("local_user", "bad/session", "simple_agent"),
        ("local_user", "s1", "bad agent"),
    ],
)
def test_touch_rejects_invalid_ids(
    tmp_path: Path, user_id: str, session_id: str, agent_id: str
) -> None:
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(plugin.touch(user_id, session_id, agent_id))


def test_new_session_rejects_invalid_user(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(plugin.new_session(".."))


def test_invalidate_closes_connection_without_running_loop(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    asyncio.run(plugin.touch("local_user", "s1", "simple_agent"))
    assert plugin._connection is not None
    plugin._invalidate(cast(Any, None))
    assert plugin._connection is None
    plugin._invalidate(cast(Any, None))


def test_invalidate_closes_connection_inside_running_loop(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    async def scenario() -> None:
        await plugin.touch("local_user", "s1", "simple_agent")
        plugin._invalidate(cast(Any, None))
        assert plugin._connection is None

    asyncio.run(scenario())


def test_plugin_info(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    assert plugin.get_plugin_info() == {
        "name": "sqlite-session-index",
        "version": "1.0.0",
    }
