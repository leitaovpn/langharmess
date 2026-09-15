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


def agent_record(agent_id: str = "simple_agent", enabled: bool = True) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "description": f"{agent_id} description",
        "enabled": enabled,
        "created_at": "2026-09-15T00:00:00+00:00",
        "updated_at": "2026-09-15T00:00:00+00:00",
    }


class FakeAgentRegistry:
    def __init__(self, agents: list[dict[str, Any]] | None = None) -> None:
        self._agents = agents if agents is not None else [agent_record()]

    def list_agents(self) -> list[dict[str, Any]]:
        return [dict(agent) for agent in self._agents]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        for agent in self._agents:
            if agent["id"] == agent_id:
                return dict(agent)
        return None


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


def make_stream_plugin(
    loop: Any = None, *, registry: Any = None, index: Any = None
) -> Any:
    plugin = StreamRoutePlugin()
    plugin._agent_loop = loop if loop is not None else FakeAgentLoop()
    descriptors: list[Any] = []
    plugin._plugin_registrar = type(
        "Registrar", (), {"ensure_plugin": lambda self, item: descriptors.append(item)}
    )()
    plugin._session_index = index if index is not None else FakeSessionIndex()
    plugin._agent_registry = registry if registry is not None else FakeAgentRegistry()
    plugin._runtime_llm_descriptors = descriptors
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
    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "local_user::session-1"
            yield {"type": "assistant", "content": "hello"}
            yield {"type": "assistant", "content": "world"}

    plugin = make_stream_plugin(FakeAgentLoop())
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
    descriptor = plugin._runtime_llm_descriptors[0]
    assert descriptor.name == "runtime-llm"
    assert descriptor.properties == {
        "plugin.model.name": "test-model",
        "plugin.model.api_key": "test-key",
        "plugin.model.base_url": "https://models.example/v1",
        "plugin.model.protocol": "chat",
    }


def test_stream_route_creates_session_when_absent() -> None:
    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "local_user::generated-session"
            yield {"type": "assistant", "content": "ok"}

    plugin = make_stream_plugin(FakeAgentLoop())
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
    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            assert thread_id == "alice::session-1"
            yield {"type": "assistant", "content": "ok"}

    plugin = make_stream_plugin(
        FakeAgentLoop(), registry=FakeAgentRegistry([agent_record("researcher")])
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
    plugin = make_stream_plugin(registry=FakeAgentRegistry())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(agent_id="missing_agent")
    )
    assert response.status_code == 400
    assert "missing_agent" in response.json()["detail"]
    assert plugin._session_index.touched == []


def test_stream_route_rejects_disabled_agent() -> None:
    plugin = make_stream_plugin(
        registry=FakeAgentRegistry([agent_record("simple_agent", enabled=False)])
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
    plugin = make_stream_plugin(registry=FakeAgentRegistry())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(**{field: value})
    )
    assert response.status_code == 400
    assert field in response.json()["detail"]


def test_stream_route_reports_missing_session_index() -> None:
    plugin = make_stream_plugin(registry=FakeAgentRegistry())
    plugin._session_index = None
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 503


def test_stream_route_reports_missing_agent_registry() -> None:
    plugin = make_stream_plugin(registry=FakeAgentRegistry())
    plugin._agent_registry = None
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload()
    )
    assert response.status_code == 503


def test_stream_route_requires_model_until_agents_own_llms() -> None:
    plugin = make_stream_plugin(registry=FakeAgentRegistry())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(model=None)
    )
    assert response.status_code == 400
    assert "model" in response.json()["detail"]
    assert plugin._session_index.touched == []


def test_stream_route_serializes_agent_errors_as_complete_ndjson() -> None:
    class FailingAgentLoop:
        async def astream(self, message, *, thread_id=None):
            yield {"type": "assistant", "content": "partial"}
            raise RuntimeError("upstream failed with test-key")

    plugin = make_stream_plugin(FailingAgentLoop())
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


def test_stream_route_passes_optional_stream_usage_to_runtime_llm() -> None:
    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            if False:
                yield None

    plugin = make_stream_plugin(FakeAgentLoop())
    response = TestClient(make_stream_app(plugin)).post(
        "/stream", json=stream_payload(stream_usage=False)
    )
    assert response.status_code == 200
    assert (
        plugin._runtime_llm_descriptors[0].properties["plugin.model.stream_usage"]
        is False
    )


def test_stream_route_serializes_runtime_model_replacement() -> None:
    state = {"active": 0, "maximum": 0}

    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            await asyncio.sleep(0.01)
            yield {"type": "assistant", "content": message}
            state["active"] -= 1

    plugin = make_stream_plugin(FakeAgentLoop())
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
    assert state["maximum"] == 1
