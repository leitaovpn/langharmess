"""Descriptors and assembly helpers for the built-in API plugins."""

from __future__ import annotations

from pathlib import Path

from langharness_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
    SPEC_SERVER_SERVER,
    SPEC_UI_SDK,
)
from langharness_plugin.package import PluginContribution, PluginPackage
from langharness_plugin.registry import PluginDescriptor


def api_auth_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-auth",
        version="1.0.0",
        module="langharness_api.plugins.auth.auth",
        factory="api-auth-plugin-factory",
        instance="api-auth",
        specification=SPEC_AUTH,
        properties={"plugin.token": "secret"},
        swap_policy="hot",
        scope="server",
        scope_parent="root",
    )


def api_rate_limit_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-rate-limit",
        version="1.0.0",
        module="langharness_api.plugins.rate_limit.rate_limit",
        factory="api-rate-limit-plugin-factory",
        instance="api-rate-limit",
        specification=SPEC_RATE_LIMIT,
        properties={"plugin.limit": 100},
        swap_policy="hot",
        scope="server",
        scope_parent="root",
    )


def api_db_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-db",
        version="1.0.0",
        module="langharness_api.plugins.db.db",
        factory="api-db-plugin-factory",
        instance="api-db",
        specification=SPEC_DB,
        scope="root",
    )


def api_health_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-health",
        version="1.0.0",
        module="langharness_api.plugins.routes.health",
        factory="api-health-plugin-factory",
        instance="api-health",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )


def api_stream_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-stream",
        version="1.0.0",
        module="langharness_api.plugins.routes.stream",
        factory="api-stream-route-factory",
        instance="api-stream",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )

def api_resume_descriptor() -> PluginDescriptor:
    return PluginDescriptor(name="api-resume", version="1.0.0", module="langharness_api.plugins.routes.resume", factory="api-resume-route-factory", instance="api-resume", specification=SPEC_ROUTE, scope="server", scope_parent="root")


def api_plugins_descriptor(directory: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="api-plugins",
        version="1.0.0",
        module="langharness_api.plugins.routes.plugins",
        factory="api-plugins-route-factory",
        instance="api-plugins",
        specification=SPEC_ROUTE,
        properties={"plugin.config_dir": directory},
        scope="server",
        scope_parent="root",
    )


def api_scopes_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-scopes",
        version="1.0.0",
        module="langharness_api.plugins.routes.scopes",
        factory="api-scopes-route-factory",
        instance="api-scopes",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )


def api_sessions_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-sessions",
        version="1.0.0",
        module="langharness_api.plugins.routes.sessions",
        factory="api-sessions-route-factory",
        instance="api-sessions",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )


def api_agents_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-agents",
        version="1.0.0",
        module="langharness_api.plugins.routes.agents",
        factory="api-agents-route-factory",
        instance="api-agents",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )


def api_server_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-server",
        version="1.0.0",
        module="langharness_api.plugins.server.app",
        factory="api-server-factory",
        instance="api-server",
        specification=SPEC_API_SERVER,
        scope="server",
        scope_parent="root",
    )


def server_server_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="server-server",
        version="1.0.0",
        module="langharness_api.plugins.server.runtime",
        factory="server-server-factory",
        instance="server-server",
        specification=SPEC_SERVER_SERVER,
        scope="server",
        scope_parent="root",
    )


def ui_sdk_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="ui-sdk",
        version="1.0.0",
        module="langharness_api.plugins.sdk.http",
        factory="http-ui-sdk-factory",
        instance="ui-sdk",
        specification=SPEC_UI_SDK,
        scope="ui",
        scope_parent="root",
    )


def sdk_package() -> PluginPackage:
    return PluginPackage(
        id="builtin.api.sdk",
        version="1.0.0",
        contributions=(PluginContribution("sdk", "ui", ui_sdk_descriptor()),),
    )


def builtin_package() -> PluginPackage:
    """Describe the API plugins already installed by the server assembly."""
    directory = str(Path.home() / ".langharness")
    return PluginPackage(
        id="builtin.api",
        version="1.0.0",
        contributions=(
            PluginContribution("auth", "server", api_auth_descriptor()),
            PluginContribution("rate-limit", "server", api_rate_limit_descriptor()),
            PluginContribution("db", "root", api_db_descriptor()),
            PluginContribution("health", "server", api_health_descriptor()),
            PluginContribution("stream", "server", api_stream_descriptor()),
            PluginContribution("resume", "server", api_resume_descriptor()),
            PluginContribution(
                "plugins", "server", api_plugins_descriptor(directory)
            ),
            PluginContribution("scopes", "server", api_scopes_descriptor()),
            PluginContribution("sessions", "server", api_sessions_descriptor()),
            PluginContribution("agents", "server", api_agents_descriptor()),
            PluginContribution("server", "server", api_server_descriptor()),
            PluginContribution(
                "server-runtime", "server", server_server_descriptor()
            ),
        ),
    )
