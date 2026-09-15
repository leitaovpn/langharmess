"""Tests for the session and agent route plugins."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from langharmess_api.plugins.routes.agents import AgentsRoutePlugin
from langharmess_api.plugins.routes.sessions import SessionsRoutePlugin

SESSION = {
    "user_id": "local_user",
    "session_id": "s1",
    "created_at": "2026-09-15T00:00:00+00:00",
    "last_used_at": "2026-09-15T00:00:00+00:00",
    "turns": 2,
    "last_agent_id": "simple_agent",
    "agents_used": ["simple_agent"],
}


class FakeSessionIndex:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def new_session(self, user_id: str) -> str:
        return "generated"

    async def touch(self, user_id: str, session_id: str, agent_id: str) -> None:
        return None

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        return SESSION if session_id == "s1" else None

    async def list_sessions(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.calls.append((user_id, limit))
        return [SESSION] if user_id == "local_user" else []


def make_client(plugin: Any) -> TestClient:
    app = FastAPI()
    app.include_router(plugin.get_router())
    return TestClient(app)


def test_sessions_route_lists_user_sessions() -> None:
    plugin = SessionsRoutePlugin()
    index = FakeSessionIndex()
    plugin._session_index = index

    response = make_client(plugin).get("/sessions", params={"user_id": "local_user"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "local_user"
    assert body["sessions"] == [SESSION]
    assert index.calls == [("local_user", 50)]


def test_sessions_route_forwards_limit() -> None:
    plugin = SessionsRoutePlugin()
    index = FakeSessionIndex()
    plugin._session_index = index

    response = make_client(plugin).get(
        "/sessions", params={"user_id": "local_user", "limit": 5}
    )

    assert response.status_code == 200
    assert index.calls == [("local_user", 5)]


def test_sessions_route_rejects_invalid_user() -> None:
    plugin = SessionsRoutePlugin()
    plugin._session_index = FakeSessionIndex()

    response = make_client(plugin).get("/sessions", params={"user_id": "bad user"})

    assert response.status_code == 400
    assert "user_id" in response.json()["detail"]


def test_sessions_route_requires_user_id() -> None:
    plugin = SessionsRoutePlugin()
    plugin._session_index = FakeSessionIndex()
    assert make_client(plugin).get("/sessions").status_code == 422


def test_sessions_route_reports_missing_index() -> None:
    response = make_client(SessionsRoutePlugin()).get(
        "/sessions", params={"user_id": "local_user"}
    )
    assert response.status_code == 503


def test_sessions_route_plugin_info() -> None:
    plugin = SessionsRoutePlugin()
    assert plugin.get_plugin_info() == {"name": "sessions", "version": "1.0.0"}


class FakeAgentRegistry:
    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "simple_agent",
                "name": "Simple Agent",
                "description": "Built-in agent.",
                "enabled": True,
                "created_at": "2026-09-15T00:00:00+00:00",
                "updated_at": "2026-09-15T00:00:00+00:00",
            }
        ]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self.list_agents()[0] if agent_id == "simple_agent" else None


def test_agents_route_lists_agents() -> None:
    plugin = AgentsRoutePlugin()
    plugin._agent_registry = FakeAgentRegistry()

    response = make_client(plugin).get("/agents")

    assert response.status_code == 200
    agents = response.json()["agents"]
    assert [agent["id"] for agent in agents] == ["simple_agent"]
    assert agents[0]["description"]


def test_agents_route_reports_missing_registry() -> None:
    assert make_client(AgentsRoutePlugin()).get("/agents").status_code == 503


def test_agents_route_plugin_info() -> None:
    plugin = AgentsRoutePlugin()
    assert plugin.get_plugin_info() == {"name": "agents", "version": "1.0.0"}
