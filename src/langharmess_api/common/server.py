"""Standalone API server factory used by uvicorn."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from langharmess_api.contracts import SPEC_API_SERVER
from langharmess_api.plugin import (
    api_agents_descriptor,
    api_auth_descriptor,
    api_db_descriptor,
    api_health_descriptor,
    api_rate_limit_descriptor,
    api_server_descriptor,
    api_sessions_descriptor,
    api_stream_descriptor,
)
from langharmess_config.plugin import config_descriptors
from langharmess_core.plugin import (
    DEFAULT_AGENT_PLUGINS,
    agent_directory_descriptor,
    agent_loop_template_descriptor,
    agent_plugin_template_descriptor,
    agent_registry_descriptor,
    session_index_descriptor,
    sqlite_checkpointer_descriptor,
)
from langharmess_logging.plugin import log_descriptor
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginRegistry

_MANAGER: PluginManager | None = None


def create_app() -> FastAPI:
    global _MANAGER

    if _MANAGER is None:
        directory = os.environ.get(
            "LANG_HARMESS_DIR", str(Path.home() / ".langharmess")
        )
        agent_templates = [
            agent_plugin_template_descriptor(plugin)
            for plugin in dict.fromkeys(("llm", *DEFAULT_AGENT_PLUGINS))
        ]
        registry = PluginRegistry(
            config_descriptors(directory)
            + [log_descriptor("server", directory)]
            + agent_templates
            + [
                agent_loop_template_descriptor(),
                agent_registry_descriptor(directory),
                agent_directory_descriptor(),
                session_index_descriptor(directory),
                api_auth_descriptor(),
                api_rate_limit_descriptor(),
                api_db_descriptor(),
                api_health_descriptor(),
                sqlite_checkpointer_descriptor(directory),
                api_agents_descriptor(),
                api_sessions_descriptor(),
                api_stream_descriptor(),
                api_server_descriptor(),
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
