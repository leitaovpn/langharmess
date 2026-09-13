"""Standalone API server factory used by uvicorn."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from langharmess_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
)
from langharmess_config.builtins import config_descriptors
from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_CHECKPOINTER, SPEC_TOOL
from langharmess_logging.builtins import log_descriptor
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry

_MANAGER: PluginManager | None = None


def create_app() -> FastAPI:
    global _MANAGER

    if _MANAGER is None:
        directory = os.environ.get(
            "LANG_HARMESS_DIR", str(Path.home() / ".langharmess")
        )
        registry = PluginRegistry(
            config_descriptors(directory)
            + [log_descriptor("server", directory)]
            + [
                PluginDescriptor(
                    name="agent-loop",
                    version="1.0.0",
                    module="langharmess_core.agent_loop",
                    factory="agent-loop-factory",
                    instance="agent-loop",
                    specification=SPEC_AGENT_LOOP,
                ),
                PluginDescriptor(
                    name="api-auth",
                    version="1.0.0",
                    module="langharmess_api.plugins.auth.template_auth",
                    factory="api-auth-template-factory",
                    instance="api-auth",
                    specification=SPEC_AUTH,
                    properties={"plugin.token": "secret"},
                ),
                PluginDescriptor(
                    name="api-rate-limit",
                    version="1.0.0",
                    module="langharmess_api.plugins.rate_limit.template_rate_limit",
                    factory="api-rate-limit-template-factory",
                    instance="api-rate-limit",
                    specification=SPEC_RATE_LIMIT,
                    properties={"plugin.limit": 100},
                ),
                PluginDescriptor(
                    name="api-db",
                    version="1.0.0",
                    module="langharmess_api.plugins.db.template_db",
                    factory="api-db-template-factory",
                    instance="api-db",
                    specification=SPEC_DB,
                ),
                PluginDescriptor(
                    name="api-health",
                    version="1.0.0",
                    module="langharmess_api.plugins.routes.template_health",
                    factory="api-health-route-template-factory",
                    instance="api-health",
                    specification=SPEC_ROUTE,
                ),
                PluginDescriptor(
                    name="sqlite-checkpointer",
                    version="1.0.0",
                    module="langharmess_core.plugins.loop.checkpointer.sqlite",
                    factory="sqlite-checkpointer-plugin-factory",
                    instance="sqlite-checkpointer",
                    specification=SPEC_CHECKPOINTER,
                    properties={
                        "plugin.checkpoint.path": "langharmess_checkpoints.sqlite3"
                    },
                ),
                PluginDescriptor(
                    name="workspace-tools",
                    version="1.0.0",
                    module="langharmess_core.plugins.loop.tools.workspace",
                    factory="workspace-tools-plugin-factory",
                    instance="workspace-tools",
                    specification=SPEC_TOOL,
                    properties={"plugin.tools.root_dir": "."},
                ),
                PluginDescriptor(
                    name="api-stream",
                    version="1.0.0",
                    module="langharmess_api.plugins.routes.stream",
                    factory="api-stream-route-factory",
                    instance="api-stream",
                    specification=SPEC_ROUTE,
                ),
                PluginDescriptor(
                    name="api-server",
                    version="1.0.0",
                    module="langharmess_api.app",
                    factory="api-server-factory",
                    instance="api-server",
                    specification=SPEC_API_SERVER,
                ),
            ]
        )
        manager = PluginManager(registry)
        manager.start()
        for descriptor in registry.list():
            manager.install_plugin(descriptor)
        _MANAGER = manager

    assert _MANAGER is not None
    api_server = _MANAGER.get_service(SPEC_API_SERVER)
    assert api_server is not None
    return cast(FastAPI, api_server.build_app())
