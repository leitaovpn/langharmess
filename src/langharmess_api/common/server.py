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
    api_plugins_descriptor,
    api_rate_limit_descriptor,
    api_server_descriptor,
    api_sessions_descriptor,
    api_stream_descriptor,
)
from langharmess_config.plugin import config_descriptors
from langharmess_core.contracts import SPEC_AGENT_DIRECTORY
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
from langharmess_plugin.config_store import (
    agent_scope_configs,
    apply_overrides,
    load_overrides,
)
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry

_MANAGER: PluginManager | None = None


def _api_descriptors(
    directory: str, agent_templates: list[PluginDescriptor]
) -> list[PluginDescriptor]:
    """Code descriptors with the stored api-scope overrides merged in."""
    overrides = load_overrides(directory, "api")
    descriptors = (
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
            api_plugins_descriptor(directory),
            api_server_descriptor(),
        ]
    )
    return [
        apply_overrides(descriptor, overrides[descriptor.name])
        if descriptor.name in overrides
        else descriptor
        for descriptor in descriptors
    ]


def _apply_agent_configs(manager: PluginManager, directory: str) -> None:
    configs = agent_scope_configs(directory)
    if not configs:
        return
    agent_directory = manager.get_service(SPEC_AGENT_DIRECTORY)
    if agent_directory is None:
        return
    for agent_id, plugins in configs:
        agent_directory.apply_agent_config(agent_id, plugins)


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
            _api_descriptors(directory, agent_templates)
        )
        manager = PluginManager(registry)
        manager.start()
        for descriptor in registry.list():
            manager.install_plugin(descriptor)
        _apply_agent_configs(manager, directory)
        _MANAGER = manager

    assert _MANAGER is not None
    api_server = _MANAGER.get_service(SPEC_API_SERVER)
    assert api_server is not None
    return cast(FastAPI, api_server.build_app())
