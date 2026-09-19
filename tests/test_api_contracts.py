"""Contract tests for API server plugin services."""

from __future__ import annotations

from types import SimpleNamespace

from langharness_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
    AuthProvider,
    DBProvider,
    RateLimitProvider,
    RouteProvider,
)
from langharness_api.plugins.auth.auth import AuthPlugin
from langharness_api.plugins.db.db import DBPlugin
from langharness_api.plugins.rate_limit.rate_limit import (
    RateLimitPlugin,
)
from langharness_api.plugins.routes.health import HealthRoutePlugin
from langharness_api.plugins.server.app import APIServerService


def test_spec_constants() -> None:
    assert SPEC_API_SERVER == "api.server"
    assert SPEC_AUTH == "api.plugin.auth"
    assert SPEC_RATE_LIMIT == "api.plugin.rate_limit"
    assert SPEC_DB == "api.plugin.db"
    assert SPEC_ROUTE == "api.plugin.route"


def test_template_plugins_conform_to_protocols() -> None:
    assert isinstance(AuthPlugin(), AuthProvider)
    assert isinstance(RateLimitPlugin(), RateLimitProvider)
    assert isinstance(DBPlugin(), DBProvider)
    assert isinstance(HealthRoutePlugin(), RouteProvider)


def test_api_server_service_builds_app() -> None:
    service = APIServerService()
    configs = object()
    messages: list[str] = []
    service._configs = configs
    service._log_provider = SimpleNamespace(
        get_logger=lambda: SimpleNamespace(info=messages.append)
    )
    app = service.build_app()
    assert app.title == "langharness_api"
    assert app.state.configs is configs
    assert app.state.log is service._log_provider
    assert messages == ["API server app built"]
