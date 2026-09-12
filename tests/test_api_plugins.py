"""Unit tests for API template plugins."""
# mypy: ignore-errors

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from langharmess_api.dependencies import get_db_session
from langharmess_api.plugins.auth.template_auth import TemplateAuthPlugin
from langharmess_api.plugins.db.template_db import TemplateDBPlugin
from langharmess_api.plugins.rate_limit.template_rate_limit import (
    TemplateRateLimitPlugin,
)
from langharmess_api.plugins.routes.template_health import TemplateHealthRoutePlugin
from langharmess_api.plugins.routes.template_stream import TemplateStreamRoutePlugin
from langharmess_core.agent_loop import PluginAgentLoop


def test_auth_plugin_rejects_missing_token() -> None:
    plugin = TemplateAuthPlugin()
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
    plugin = TemplateAuthPlugin()
    plugin._token = "secret"
    dependency = plugin.get_auth_dependency()
    request = Request(
        {"type": "http", "headers": [(b"authorization", b"Bearer secret")]}
    )
    assert dependency(request) == "secret"


def test_rate_limit_plugin_enforces_limit() -> None:
    plugin = TemplateRateLimitPlugin()
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
    plugin = TemplateDBPlugin()
    dependency = plugin.get_session_dependency()
    assert dependency() == {"connected": True}


def test_health_route_has_router_and_dependency() -> None:
    plugin = TemplateHealthRoutePlugin()
    router = plugin.get_router()
    assert router is not None
    assert get_db_session is not None


def test_agent_loop_astream_yields_message_contents() -> None:
    class FakeGraph:
        async def astream(self, input_data, stream_mode=None):
            yield (type("M", (), {"content": "hello"})(), "metadata")
            yield (type("M", (), {"content": "world"})(), "metadata")

    loop = PluginAgentLoop()
    loop._graph = FakeGraph()

    async def collect():
        return [chunk async for chunk in loop.astream("hi")]

    import asyncio

    assert asyncio.run(collect()) == ["hello", "world"]


def test_stream_route_plugin_streams_agent_output() -> None:
    class FakeAgentLoop:
        async def astream(self, message):
            yield "hello"
            yield "world"

    plugin = TemplateStreamRoutePlugin()
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
        },
    )
    assert response.status_code == 200
    assert response.text == "helloworld"
    assert descriptors[0].name == "runtime-llm"
    assert descriptors[0].properties == {
        "plugin.model.name": "test-model",
        "plugin.model.api_key": "test-key",
        "plugin.model.base_url": "https://models.example/v1",
    }
