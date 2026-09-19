"""Unit tests for the JSON-backed agent registry plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from langharness_core.plugins.agents.registry import AgentRegistryPlugin


def make_plugin(tmp_path: Path) -> AgentRegistryPlugin:
    plugin = AgentRegistryPlugin()
    plugin._path = str(tmp_path / "agents.json")
    return plugin


def test_list_agents_seeds_simple_agent(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    agents = plugin.list_agents()
    assert [agent["id"] for agent in agents] == ["simple_agent"]
    simple = agents[0]
    assert simple["name"]
    assert simple["description"]
    assert simple["enabled"] is True
    assert simple["created_at"]
    assert simple["updated_at"]


def test_list_agents_writes_seed_file_once(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.list_agents()
    path = tmp_path / "agents.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert [agent["id"] for agent in payload["agents"]] == ["simple_agent"]

    plugin.list_agents()
    payload_again = json.loads(path.read_text(encoding="utf-8"))
    assert payload_again == payload


def test_list_agents_keeps_configured_entries(tmp_path: Path) -> None:
    path = tmp_path / "agents.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "agents": [
                    {
                        "id": "researcher",
                        "name": "Researcher",
                        "description": "Reads a lot",
                        "enabled": True,
                        "created_at": "2026-09-15T00:00:00+00:00",
                        "updated_at": "2026-09-15T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plugin = make_plugin(tmp_path)
    assert [agent["id"] for agent in plugin.list_agents()] == ["researcher"]


def test_get_agent_returns_entry(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    agent = plugin.get_agent("simple_agent")
    assert agent is not None
    assert agent["id"] == "simple_agent"


def test_get_agent_returns_none_for_unknown(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    assert plugin.get_agent("missing_agent") is None


@pytest.mark.parametrize("agent_id", ["..", "bad agent", "with/slash", ""])
def test_get_agent_rejects_invalid_ids(tmp_path: Path, agent_id: str) -> None:
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        plugin.get_agent(agent_id)


def test_list_agents_rejects_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "agents.json"
    path.write_text("{not json", encoding="utf-8")
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        plugin.list_agents()


def test_list_agents_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"schema": 2, "agents": []}), encoding="utf-8")
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        plugin.list_agents()


def test_validate_seeds_registry_file(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin._validate(cast(Any, None))
    assert (tmp_path / "agents.json").exists()
    assert plugin.list_agents()[0]["id"] == "simple_agent"


def test_plugin_info(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    assert plugin.get_plugin_info() == {"name": "agent-registry", "version": "1.0.0"}


def test_create_agent_appends_entry(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.list_agents()

    created = plugin.create_agent("researcher", "Researcher", "Reads a lot")

    assert created["id"] == "researcher"
    assert created["enabled"] is True
    assert [agent["id"] for agent in plugin.list_agents()] == [
        "simple_agent",
        "researcher",
    ]


def test_create_agent_rejects_duplicates(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.list_agents()
    with pytest.raises(ValueError, match="already exists"):
        plugin.create_agent("simple_agent", "Again", "dup")


def test_update_agent_changes_fields(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.create_agent("researcher", "Researcher", "Reads a lot")

    updated = plugin.update_agent(
        "researcher", name="Deep Researcher", enabled=False
    )

    assert updated["name"] == "Deep Researcher"
    assert updated["enabled"] is False
    stored = plugin.get_agent("researcher")
    assert stored is not None
    assert stored["enabled"] is False


def test_update_agent_rejects_unknown(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    with pytest.raises(KeyError):
        plugin.update_agent("ghost", name="Ghost")


def test_delete_agent_removes_entry(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.create_agent("researcher", "Researcher", "Reads a lot")

    plugin.delete_agent("researcher")

    assert plugin.get_agent("researcher") is None
    with pytest.raises(KeyError):
        plugin.delete_agent("researcher")


def test_create_agent_rejects_invalid_id(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    with pytest.raises(ValueError):
        plugin.create_agent("bad id", "Bad", "nope")
