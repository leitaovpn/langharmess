"""Unit tests for API template plugins."""
# mypy: ignore-errors

from __future__ import annotations

from fastapi import HTTPException, Request

from langharmess_api.dependencies import get_db_session
from langharmess_api.plugins.auth.template_auth import TemplateAuthPlugin
from langharmess_api.plugins.db.template_db import TemplateDBPlugin
from langharmess_api.plugins.rate_limit.template_rate_limit import (
    TemplateRateLimitPlugin,
)
from langharmess_api.plugins.routes.template_health import TemplateHealthRoutePlugin


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
