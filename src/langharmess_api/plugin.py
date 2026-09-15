"""Descriptors and assembly helpers for the built-in API plugins."""

from __future__ import annotations

from langharmess_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
)
from langharmess_plugin.registry import PluginDescriptor


def api_auth_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-auth",
        version="1.0.0",
        module="langharmess_api.plugins.auth.auth",
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
        module="langharmess_api.plugins.rate_limit.rate_limit",
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
        module="langharmess_api.plugins.db.db",
        factory="api-db-plugin-factory",
        instance="api-db",
        specification=SPEC_DB,
        scope="root",
    )


def api_health_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-health",
        version="1.0.0",
        module="langharmess_api.plugins.routes.health",
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
        module="langharmess_api.plugins.routes.stream",
        factory="api-stream-route-factory",
        instance="api-stream",
        specification=SPEC_ROUTE,
        scope="server",
        scope_parent="root",
    )


def api_plugins_descriptor(directory: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="api-plugins",
        version="1.0.0",
        module="langharmess_api.plugins.routes.plugins",
        factory="api-plugins-route-factory",
        instance="api-plugins",
        specification=SPEC_ROUTE,
        properties={"plugin.config_dir": directory},
        scope="server",
        scope_parent="root",
    )


def api_sessions_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="api-sessions",
        version="1.0.0",
        module="langharmess_api.plugins.routes.sessions",
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
        module="langharmess_api.plugins.routes.agents",
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
        module="langharmess_api.plugins.server.app",
        factory="api-server-factory",
        instance="api-server",
        specification=SPEC_API_SERVER,
        scope="server",
        scope_parent="root",
    )
