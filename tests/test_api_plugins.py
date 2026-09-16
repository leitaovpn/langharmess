"""Unit tests for API template plugins."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from langharmess_api.plugins.auth.auth import AuthPlugin
from langharmess_api.plugins.db.db import DBPlugin
from langharmess_api.plugins.rate_limit.rate_limit import (
    RateLimitPlugin,
)
from langharmess_api.plugins.routes.health import HealthRoutePlugin
from langharmess_api.plugins.routes.stream import StreamRoutePlugin
from langharmess_core.common.dependencies import get_db_session
from langharmess_core.plugins.loop.agent_loop import PluginAgentLoop


def agent_record(
    agent_id: str = "simple_agent", enabled: bool = True
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "description": f"{agent_id} description",
        "enabled": enabled,
        "created_at": "2026-09-15T00:00:00+00:00",
        "updated_at": "2026-09-15T00:00:00+00:00",
    }


class FakeSessionIndex:
    def __init__(self) -> None:
        self.touched: list[tuple[str, str, str]] = []

    async def new_session(self, user_id: str) -> str:
        return "generated-session"

    async def touch(self, user_id: str, session_id: str, agent_id: str) -> None:
        self.touched.append((user_id, session_id, agent_id))

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        return None

    async def list_sessions(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return []


class FakeAgentLoop:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply

    async def astream(self, message: str, *, thread_id: str | None = None) -> Any:
        yield {"type": "assistant", "content": self.reply}


class FakeDirectory:
    """Stands in for the agent directory: per-agent loops and plugin sets."""

    def __init__(self, agents: dict[str, bool] | None = None) -> None:
        self.agents = agents if agents is not None else {"simple_agent": True}
        self.llm_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.loops: dict[str, Any] = {}
        self.stored: dict[str, dict[str, dict[str, Any]]] = {}

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            agent_record(agent_id, enabled)
            for agent_id, enabled in self.agents.items()
        ]

    def get_loop(self, agent_id: str) -> Any:
        return self.loops.get(agent_id)

    def binding_properties(self, agent_id: str, plugin: str) -> dict[str, Any]:
        return dict(self.stored.get(agent_id, {}).get(plugin, {}))

    def apply_agent_config(self, agent_id: str, plugins: dict[str, Any]) -> None:
        return None

    def ensure_plugin_instance(
        self, agent_id: str, plugin: str, properties: dict[str, Any]
    ) -> None:
        if agent_id not in self.agents:
            raise ValueError(f"Unknown agent: {agent_id}")
        if not self.agents[agent_id]:
            raise ValueError(f"Agent is disabled: {agent_id}")
        self.llm_calls.append((agent_id, plugin, properties))
        self.loops.setdefault(agent_id, FakeAgentLoop())

    def reload(self, agent_id: str | None = None) -> None:
        return None


def make_stream_plugin(
    loop: Any = None, *, directory: Any = None, index: Any = None
) -> Any:
    plugin = StreamRoutePlugin()
    fake_directory = directory if directory is not None else FakeDirectory()
    if loop is not None:
        fake_directory.loops["simple_agent"] = loop
    plugin._agent_directory = fake_directory
    plugin._session_index = index if index is not None else FakeSessionIndex()
    return plugin


def make_stream_app(plugin: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(plugin.get_router())
    return app


def stream_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": "hi",
        "model": "test-model",
        "api_key": "test-key",
        "base_url": "https://models.example/v1",
        "session_id": "session-1",
    }
    payload.update(overrides)
    return payload


def ndjson_events(response: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in response.text.splitlines()]


def test_auth_plugin_rejects_missing_token() -> None:
    plugin = AuthPlugin()
    plugin._token = "secret"
    dependency = plugin.get_auth_dependency()
    request = Request({"type": "http", "headers": []})
    try:
        dependency(request)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing token should raise 401")


def test_auth_plugin_accepts_correct_token() -> None:
    plugin = AuthPlugin()
    plugin._token = "secret"
    dependency = plugin.get_auth_dependency()
    request = Request(
        {"type": "http", "headers": [(b"authorization", b"Bearer secret")]}
    )
    assert dependency(request) == "secret"


def test_rate_limit_plugin_enforces_limit() -> None:
    plugin = RateLimitPlugin()
    plugin._limit = 2
    dependency = plugin.get_rate_limit_dependency()
    request = Request({"type": "http", "client": ("127.0.0.1", 1234)})
    dependency(request)
    dependency(request)
    try:
        dependency(request)
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("rate limit should raise 429")


def test_db_plugin_returns_session() -> None:
    plugin = DBPlugin()
    dependency = plugin.get_session_dependency()
    assert dependency() == {"connected": True}


def test_health_route_has_router_and_dependency() -> None:
    plugin = HealthRoutePlugin()
    router = plugin.get_router()
    assert router is not None
    assert get_db_session is not None


def test_agent_loop_astream_yields_message_contents() -> None:
    class FakeGraph:
        async def astream(self, input_data, config=None, stream_mode=None):
            yield ("messages", (AIMessage(content="hello"), "metadata"))
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "bash",
                                        "args": {"commands": "pwd"},
                                        "id": "call-1",
                                        "type": "tool_call",
                                    }
                                ],
                            )
                        ]
                    }
                },
            )
            yield (
                "updates",
                {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content="/workspace",
                                name="bash",
                                tool_call_id="call-1",
                            )
                        ]
                    }
                },
            )

    loop = PluginAgentLoop()
    loop._graph = FakeGraph()

    async def collect():
        return [chunk async for chunk in loop.astream("hi")]

    import asyncio

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "hello"},
        {
            "type": "tool_call",
            "name": "bash",
            "tool_call_id": "call-1",
            "args": {"commands": "pwd"},
        },
        {
            "type": "tool_output",
            "name": "bash",
            "tool_call_id": "call-1",
            "output": "/workspace",
        },
    ]


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        (["A", "AB", "ABC"], ["A", "B", "C"]),
        (["A", "B", "C"], ["A", "B", "C"]),
    ],
)
def test_agent_loop_astream_normalizes_assistant_content_to_deltas(
    contents: list[str], expected: list[str]
) -> None:
    class FakeGraph:
        async def astream(self, input_data, config=None, stream_mode=None):
            for content in contents:
                yield (
                    "messages",
                    (AIMessageChunk(content=content, id="response-1"), "metadata"),
                )

    loop = PluginAgentLoop()
    loop._graph = FakeGraph()

    async def collect():
        return [chunk async for chunk in loop.astream("hi")]

    import asyncio

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": content} for content in expected
    ]


def test_agent_loop_astream_extracts_responses_api_text_blocks() -> None:
    class FakeGraph:
        async def astream(self, input_data, config=None, stream_mode=None):
            yield (
                "messages",
                (
                    AIMessageChunk(
                        content=[{"type": "text", "text": "responses-ok", "index": 0}],
                        id="response-1",
                    ),
                    "metadata",
                ),
            )
            yield ("messages", (AIMessageChunk(content=[], id="response-1"), "metadata"))

    loop = PluginAgentLoop()
    loop._graph = FakeGraph()

    async def collect():
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "responses-ok"}
    ]


def test_stream_route_plugin_streams_agent_output() -> None:
    class FakeLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "local_user::simple_agent::session-1"
            yield {"type": "assistant", "content": "hello"}
            yield {"type": "assistant", "content": "world"}

    plugin = make_stream_plugin(FakeLoop())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )

    assert response.status_code == 200
    events = ndjson_events(response)
    assert events[0] == {
        "type": "session",
        "session_id": "session-1",
        "agent_id": "simple_agent",
        "user_id": "local_user",
    }
    assert events[1:] == [
        {"type": "assistant", "content": "hello"},
        {"type": "assistant", "content": "world"},
    ]
    assert plugin._session_index.touched == [
        ("local_user", "session-1", "simple_agent")
    ]
    agent_id, plugin_key, properties = plugin._agent_directory.llm_calls[0]
    assert (agent_id, plugin_key) == ("simple_agent", "llm")
    assert properties == {
        "plugin.model.name": "test-model",
        "plugin.model.api_key": "test-key",
        "plugin.model.base_url": "https://models.example/v1",
        "plugin.model.protocol": "chat",
    }


def test_stream_route_scopes_llm_configuration_per_agent() -> None:
    plugin = make_stream_plugin(
        directory=FakeDirectory({"simple_agent": True, "researcher": True})
    )
    client = TestClient(make_stream_app(plugin))

    client.post("/stream", json=stream_payload(agent_id="researcher"))
    client.post("/stream", json=stream_payload(agent_id="simple_agent"))

    assert [call[0] for call in plugin._agent_directory.llm_calls] == [
        "researcher",
        "simple_agent",
    ]


def test_stream_route_creates_session_when_absent() -> None:
    class FakeLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "local_user::generated-session"
            yield {"type": "assistant", "content": "ok"}

    plugin = make_stream_plugin(FakeLoop())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(session_id=None)
    )

    assert response.status_code == 200
    events = ndjson_events(response)
    assert events[0] == {
        "type": "session",
        "session_id": "generated-session",
        "agent_id": "simple_agent",
        "user_id": "local_user",
    }
    assert plugin._session_index.touched == [
        ("local_user", "generated-session", "simple_agent")
    ]


def test_stream_route_honours_explicit_user_and_agent() -> None:
    class FakeLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "alice::session-1"
            yield {"type": "assistant", "content": "ok"}

    plugin = make_stream_plugin(
        FakeLoop(), directory=FakeDirectory({"researcher": True})
    )
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(user_id="alice", agent_id="researcher")
    )

    assert response.status_code == 200
    assert ndjson_events(response)[0] == {
        "type": "session",
        "session_id": "session-1",
        "agent_id": "researcher",
        "user_id": "alice",
    }
    assert plugin._session_index.touched == [("alice", "session-1", "researcher")]


def test_stream_route_rejects_unknown_agent() -> None:
    plugin = make_stream_plugin()
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(agent_id="missing_agent")
    )
    assert response.status_code == 400
    assert "missing_agent" in response.json()["detail"]
    assert plugin._session_index.touched == []


def test_stream_route_rejects_disabled_agent() -> None:
    plugin = make_stream_plugin(
        directory=FakeDirectory({"simple_agent": False})
    )
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 400
    assert "simple_agent" in response.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", "bad user"),
        ("agent_id", "bad agent"),
        ("session_id", "bad/session"),
    ],
)
def test_stream_route_rejects_invalid_identifiers(field: str, value: str) -> None:
    plugin = make_stream_plugin()
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(**{field: value})
    )
    assert response.status_code == 400
    assert field in response.json()["detail"]


def test_stream_route_reports_missing_session_index() -> None:
    plugin = make_stream_plugin()
    plugin._session_index = None
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 503


def test_stream_route_reports_missing_directory() -> None:
    plugin = make_stream_plugin()
    plugin._agent_directory = None
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 503


def test_stream_route_reports_missing_loop() -> None:
    plugin = make_stream_plugin()
    plugin._agent_directory.loops.clear()
    original = plugin._agent_directory.ensure_plugin_instance

    def ensure_without_loop(agent_id: str, plugin_key: str, properties: Any) -> None:
        original(agent_id, plugin_key, properties)
        plugin._agent_directory.loops.clear()

    plugin._agent_directory.ensure_plugin_instance = ensure_without_loop
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 503


def test_stream_route_requires_model_until_agents_own_llms() -> None:
    plugin = make_stream_plugin()
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(model=None)
    )
    assert response.status_code == 400
    assert "model" in response.json()["detail"]
    assert plugin._session_index.touched == []


def test_stream_route_accepts_agent_configured_llm_without_request_model() -> None:
    plugin = make_stream_plugin()
    plugin._agent_directory.stored = {
        "simple_agent": {"llm": {"plugin.model.name": "stored-model"}}
    }

    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(model=None)
    )

    assert response.status_code == 200
    properties = plugin._agent_directory.llm_calls[0][2]
    assert "plugin.model.name" not in properties


def test_stream_route_serializes_agent_errors_as_complete_ndjson() -> None:
    class FailingLoop:
        async def astream(self, message, *, thread_id=None):
            yield {"type": "assistant", "content": "partial"}
            raise RuntimeError("upstream failed with test-key")

    plugin = make_stream_plugin(FailingLoop())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )

    assert response.status_code == 200
    assert ndjson_events(response) == [
        {
            "type": "session",
            "session_id": "session-1",
            "agent_id": "simple_agent",
            "user_id": "local_user",
        },
        {"type": "assistant", "content": "partial"},
        {
            "type": "error",
            "error_type": "RuntimeError",
            "message": "upstream failed with ***",
        },
    ]


def test_stream_route_passes_optional_stream_usage_to_the_agent_llm() -> None:
    class FakeLoop:
        async def astream(self, message, *, thread_id=None):
            if False:
                yield None

    plugin = make_stream_plugin(FakeLoop())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(stream_usage=False)
    )
    assert response.status_code == 200
    assert (
        plugin._agent_directory.llm_calls[0][2]["plugin.model.stream_usage"] is False
    )


def test_stream_route_streams_concurrently_after_configuration() -> None:
    state = {"active": 0, "maximum": 0}

    class SlowLoop:
        async def astream(self, message, *, thread_id=None):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            await asyncio.sleep(0.01)
            yield {"type": "assistant", "content": message}
            state["active"] -= 1

    plugin = make_stream_plugin(SlowLoop())
    app = make_stream_app(plugin)

    async def invoke_both() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            payload = {
                "model": "test",
                "api_key": "key",
                "base_url": "http://model",
                "session_id": "session",
            }
            await asyncio.gather(
                client.post("/stream", json={**payload, "input": "one"}),
                client.post("/stream", json={**payload, "input": "two"}),
            )

    asyncio.run(invoke_both())
    assert state["maximum"] == 2
