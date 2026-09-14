"""Unit tests for API template plugins."""
# mypy: ignore-errors

from __future__ import annotations

import asyncio

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
            assert thread_id == "session-1"
            yield {"type": "assistant", "content": "hello"}
            yield {"type": "assistant", "content": "world"}

    plugin = StreamRoutePlugin()
    plugin._agent_loop = FakeAgentLoop()
    descriptors = []
    plugin._plugin_registrar = type(
        "Registrar", (), {"ensure_plugin": lambda self, item: descriptors.append(item)}
    )()
    app = FastAPI()
    app.include_router(plugin.get_router())

    client = TestClient(app)
    response = client.post(
        "/stream",
        json={
            "input": "hi",
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "https://models.example/v1",
            "session_id": "session-1",
        },
    )
    assert response.status_code == 200
    assert response.text == (
        '{"type": "assistant", "content": "hello"}\n'
        '{"type": "assistant", "content": "world"}\n'
    )
    assert descriptors[0].name == "runtime-llm"
    assert descriptors[0].properties == {
        "plugin.model.name": "test-model",
        "plugin.model.api_key": "test-key",
        "plugin.model.base_url": "https://models.example/v1",
        "plugin.model.protocol": "chat",
    }


def test_stream_route_serializes_agent_errors_as_complete_ndjson() -> None:
    class FailingAgentLoop:
        async def astream(self, message, *, thread_id=None):
            yield {"type": "assistant", "content": "partial"}
            raise RuntimeError("upstream failed with test-key")

    plugin = StreamRoutePlugin()
    plugin._agent_loop = FailingAgentLoop()
    plugin._plugin_registrar = type(
        "Registrar", (), {"ensure_plugin": lambda self, item: None}
    )()
    app = FastAPI()
    app.include_router(plugin.get_router())

    response = TestClient(app).post(
        "/stream",
        json={
            "input": "hi",
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "https://models.example/v1",
            "session_id": "session-1",
        },
    )

    assert response.status_code == 200
    assert response.text == (
        '{"type": "assistant", "content": "partial"}\n'
        '{"type": "error", "error_type": "RuntimeError", '
        '"message": "upstream failed with ***"}\n'
    )


def test_stream_route_passes_optional_stream_usage_to_runtime_llm() -> None:
    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            if False:
                yield None

    plugin = StreamRoutePlugin()
    plugin._agent_loop = FakeAgentLoop()
    descriptors = []
    plugin._plugin_registrar = type(
        "Registrar", (), {"ensure_plugin": lambda self, item: descriptors.append(item)}
    )()
    app = FastAPI()
    app.include_router(plugin.get_router())

    client = TestClient(app)
    response = client.post(
        "/stream",
        json={
            "input": "hi",
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "https://models.example/v1",
            "session_id": "session-1",
            "stream_usage": False,
        },
    )
    assert response.status_code == 200
    assert descriptors[0].properties["plugin.model.stream_usage"] is False


def test_stream_route_serializes_runtime_model_replacement() -> None:
    state = {"active": 0, "maximum": 0}

    class FakeAgentLoop:
        async def astream(self, message, *, thread_id=None):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            await asyncio.sleep(0.01)
            yield {"type": "assistant", "content": message}
            state["active"] -= 1

    plugin = StreamRoutePlugin()
    plugin._agent_loop = FakeAgentLoop()
    plugin._plugin_registrar = type(
        "Registrar", (), {"ensure_plugin": lambda self, item: None}
    )()
    app = FastAPI()
    app.include_router(plugin.get_router())

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
