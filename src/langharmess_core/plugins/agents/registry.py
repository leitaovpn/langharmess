"""JSON-backed agent registry plugin."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Validate

from langharmess_core.common.ids import validate_id
from langharmess_core.contracts import AgentRegistryProvider

DEFAULT_AGENT_ID = "simple_agent"
DEFAULT_AGENT_NAME = "Simple Agent"
DEFAULT_AGENT_DESCRIPTION = "Built-in agent backed by the default plugin set."
_SCHEMA = 1


def default_agent() -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    return {
        "id": DEFAULT_AGENT_ID,
        "name": DEFAULT_AGENT_NAME,
        "description": DEFAULT_AGENT_DESCRIPTION,
        "enabled": True,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


@ComponentFactory("agent-registry-plugin-factory")
@Provides(AgentRegistryProvider)
@Property("_plugin_name", "plugin.name", "agent-registry")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_path", "plugin.agents.path", "~/.langharmess/agents.json")
class AgentRegistryPlugin:
    """Stores agent identity entries in a schema-versioned JSON document."""

    def __init__(self) -> None:
        self._plugin_name = "agent-registry"
        self._plugin_version = "1.0.0"
        self._path = "~/.langharmess/agents.json"

    @Validate
    def _validate(self, bundle_context: Any) -> None:
        self._ensure_file()

    def list_agents(self) -> list[dict[str, Any]]:
        return [dict(agent) for agent in self._read()["agents"]]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        wanted = validate_id(agent_id, field="agent_id")
        for agent in self._read()["agents"]:
            if agent.get("id") == wanted:
                return dict(agent)
        return None

    def _read(self) -> dict[str, Any]:
        path = self._ensure_file()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid agent registry file: {path}") from exc
        if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
            raise ValueError(f"Unsupported agent registry schema in {path}")
        if not isinstance(payload.get("agents"), list):
            raise ValueError(f"Invalid agent registry file: {path}")
        return payload

    def _ensure_file(self) -> Path:
        path = Path(self._path).expanduser()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": _SCHEMA, "agents": [default_agent()]}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
