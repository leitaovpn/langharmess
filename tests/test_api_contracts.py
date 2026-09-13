"""Contract tests for API server plugin services."""

from __future__ import annotations

from types import SimpleNamespace

from langharmess_api.app import APIServerService
from langharmess_api.contracts import (
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
from langharmess_api.plugins.auth.template_auth import TemplateAuthPlugin
from langharmess_api.plugins.db.template_db import TemplateDBPlugin
from langharmess_api.plugins.rate_limit.template_rate_limit import (
    TemplateRateLimitPlugin,
)
from langharmess_api.plugins.routes.template_health import TemplateHealthRoutePlugin


def test_spec_constants() -> None:
    assert SPEC_API_SERVER == "api.server"
    assert SPEC_AUTH == "api.plugin.auth"
    assert SPEC_RATE_LIMIT == "api.plugin.rate_limit"
    assert SPEC_DB == "api.plugin.db"
    assert SPEC_ROUTE == "api.plugin.route"


def test_template_plugins_conform_to_protocols() -> None:
    assert isinstance(TemplateAuthPlugin(), AuthProvider)
    assert isinstance(TemplateRateLimitPlugin(), RateLimitProvider)
    assert isinstance(TemplateDBPlugin(), DBProvider)
    assert isinstance(TemplateHealthRoutePlugin(), RouteProvider)


def test_api_server_service_builds_app() -> None:
    service = APIServerService()
    configs = object()
    messages: list[str] = []
    service._configs = configs
    service._log_provider = SimpleNamespace(
        get_logger=lambda: SimpleNamespace(info=messages.append)
    )
    app = service.build_app()
    assert app.title == "langharmess_api"
    assert app.state.configs is configs
    assert app.state.log is service._log_provider
    assert messages == ["API server app built"]
