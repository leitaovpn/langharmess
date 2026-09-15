"""Tests for the plugin configuration route."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from langharmess_api.plugins.routes.plugins import PluginsRoutePlugin
from langharmess_plugin.config_store import PluginConfigStore, scope_path


class FakeScopeRegistrar:
    def __init__(self) -> None:
        self.applied: list[dict[str, Any]] = []

    def instantiate_instance(self, descriptor: Any) -> None:
        return None

    def kill_instance(self, instance: str) -> None:
        return None

    def find_service(self, specification: str, filter: str | None = None) -> Any:
        return None

    def installed_modules(self) -> set[str]:
        return set()

    def apply_config(self, overrides: dict[str, Any]) -> dict[str, list[str]]:
        self.applied.append(overrides)
        return {"applied": sorted(overrides), "restart_required": []}


class FakeDirectory:
    def __init__(self) -> None:
        self.configs: list[tuple[str, dict[str, Any]]] = []

    def list_agents(self) -> list[dict[str, Any]]:
        return []

    def get_loop(self, agent_id: str) -> Any:
        return None

    def ensure_plugin_instance(
        self, agent_id: str, plugin: str, properties: dict[str, Any]
    ) -> None:
        return None

    def binding_properties(self, agent_id: str, plugin: str) -> dict[str, Any]:
        return {}

    def apply_agent_config(self, agent_id: str, plugins: dict[str, Any]) -> None:
        self.configs.append((agent_id, plugins))

    def reload(self, agent_id: str | None = None) -> None:
        return None


def make_plugin(tmp_path: Path) -> PluginsRoutePlugin:
    plugin = PluginsRoutePlugin()
    plugin._config_dir = str(tmp_path)
    plugin._scope = FakeScopeRegistrar()
    plugin._directory = FakeDirectory()
    return plugin


def make_client(plugin: PluginsRoutePlugin) -> TestClient:
    app = FastAPI()
    app.include_router(plugin.get_router())
    return TestClient(app)


def test_get_plugins_returns_current_scope_config(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    store = PluginConfigStore.load(scope_path(str(tmp_path), "api"), "api")
    store.update(
        {"api-rate-limit": {"enabled": True, "properties": {"plugin.limit": 5}}},
        actor="cli",
    )

    response = make_client(plugin).get("/plugins", params={"scope": "api"})

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "api"
    assert body["version"] == 2
    assert body["plugins"] == {
        "api-rate-limit": {"enabled": True, "properties": {"plugin.limit": 5}}
    }


def test_get_plugins_creates_missing_scope_file(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    response = make_client(plugin).get("/plugins", params={"scope": "agent:alpha"})
    assert response.status_code == 200
    assert response.json()["plugins"] == {}
    assert scope_path(str(tmp_path), "agent:alpha").exists()


def test_get_plugins_rejects_unknown_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    assert make_client(plugin).get("/plugins", params={"scope": "wat"}).status_code == 400


def test_put_plugins_applies_api_scope_overrides(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "api"},
        json={
            "actor": "cli",
            "plugins": {
                "api-rate-limit": {"enabled": True, "properties": {"plugin.limit": 9}}
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] == ["api-rate-limit"]
    assert body["restart_required"] == []
    assert body["version"] == 2
    assert plugin._scope.applied == [
        {"api-rate-limit": {"enabled": True, "properties": {"plugin.limit": 9}}}
    ]
    stored = json.loads(scope_path(str(tmp_path), "api").read_text(encoding="utf-8"))
    assert stored["history"][-1]["actor"] == "cli"


def test_put_plugins_reroutes_agent_scope_to_the_directory(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "agent:alpha"},
        json={"actor": "cli", "plugins": {"tools": {"enabled": False}}},
    )

    assert response.status_code == 200
    assert response.json()["applied"] == ["tools"]
    assert plugin._directory.configs == [("alpha", {"tools": {"enabled": False}})]
    assert plugin._scope.applied == []


def test_put_plugins_reports_restart_for_cli_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "cli"},
        json={"actor": "cli", "plugins": {"cli-rich-renderer": {"enabled": False}}},
    )

    assert response.status_code == 200
    assert response.json()["applied"] == []
    assert response.json()["restart_required"] == ["cli-rich-renderer"]
    assert plugin._scope.applied == []


def test_put_plugins_reports_unknown_plugin(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    def reject(overrides: dict[str, Any]) -> dict[str, list[str]]:
        raise ValueError("Unknown plugin: ghost")

    plugin._scope.apply_config = reject
    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "api"},
        json={"actor": "cli", "plugins": {"ghost": {"enabled": True}}},
    )

    assert response.status_code == 400
    assert "ghost" in response.json()["detail"]
    store = PluginConfigStore.load(scope_path(str(tmp_path), "api"), "api")
    assert store.plugins() == {}
    assert store.current_seq() == 1


def test_put_plugins_requires_plugins_payload(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    response = make_client(plugin).put(
        "/plugins", params={"scope": "api"}, json={"actor": "cli"}
    )
    assert response.status_code == 400


def test_history_and_rollback_round_trip(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    client = make_client(plugin)
    client.put(
        "/plugins",
        params={"scope": "api"},
        json={"actor": "cli", "plugins": {"api-auth": {"enabled": True}}},
    )
    client.put(
        "/plugins",
        params={"scope": "api"},
        json={"actor": "cli", "plugins": {"api-auth": {"enabled": False}}},
    )

    history = client.get("/plugins/history", params={"scope": "api"}).json()["history"]
    assert [entry["seq"] for entry in history] == [1, 2, 3]
    assert [entry["action"] for entry in history] == ["init", "set", "set"]

    rollback = client.post(
        "/plugins/rollback",
        params={"scope": "api"},
        json={"actor": "cli", "seq": 2},
    )

    assert rollback.status_code == 200
    assert rollback.json()["version"] == 4
    assert rollback.json()["applied"] == ["api-auth"]
    current = client.get("/plugins", params={"scope": "api"}).json()["plugins"]
    assert current == {"api-auth": {"enabled": True}}
    last = client.get("/plugins/history", params={"scope": "api"}).json()["history"][-1]
    assert last["action"] == "rollback"
    assert last["target_seq"] == 2


def test_rollback_rejects_unknown_version(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    response = make_client(plugin).post(
        "/plugins/rollback",
        params={"scope": "api"},
        json={"actor": "cli", "seq": 99},
    )
    assert response.status_code == 404


def test_plugin_info(tmp_path: Path) -> None:
    assert make_plugin(tmp_path).get_plugin_info() == {
        "name": "plugins",
        "version": "1.0.0",
    }


def test_put_plugins_rejects_unknown_scope(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    response = make_client(plugin).put(
        "/plugins", params={"scope": "wat"}, json={"actor": "cli", "plugins": {}}
    )
    assert response.status_code == 400


def test_agent_scope_requires_directory(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin._directory = None
    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "agent:alpha"},
        json={"actor": "cli", "plugins": {"tools": {"enabled": False}}},
    )
    assert response.status_code == 503


def test_agent_scope_reports_directory_errors(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    def reject(agent_id: str, plugins: dict[str, Any]) -> None:
        raise ValueError("Unknown agent: alpha")

    plugin._directory.apply_agent_config = reject
    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "agent:alpha"},
        json={"actor": "cli", "plugins": {"tools": {"enabled": False}}},
    )
    assert response.status_code == 400
    assert "Unknown agent" in response.json()["detail"]


def test_api_scope_requires_scope_service(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin._scope = None
    response = make_client(plugin).put(
        "/plugins",
        params={"scope": "api"},
        json={"actor": "cli", "plugins": {"api-auth": {"enabled": True}}},
    )
    assert response.status_code == 503


def test_route_bind_and_unbind_callbacks(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    scope = plugin._scope
    directory = plugin._directory

    plugin._on_scope_bind("_scope", scope, None)
    plugin._on_directory_bind("_directory", directory, None)
    plugin._on_scope_unbind("_scope", scope, None)
    plugin._on_directory_unbind("_directory", directory, None)

    # iPOPO clears the injected field before firing the callback, so the route
    # keeps working once the service is bound again.
    plugin._on_scope_bind("_scope", scope, None)
    plugin._on_directory_bind("_directory", directory, None)
    assert make_client(plugin).get("/plugins", params={"scope": "api"}).status_code == 200
