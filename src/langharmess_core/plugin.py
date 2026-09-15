"""Descriptors and assembly helpers for the built-in core plugins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_AGENT_REGISTRY,
    SPEC_CHECKPOINTER,
    SPEC_LLM,
    SPEC_SESSION_INDEX,
    SPEC_TOOL,
)
from langharmess_plugin.registry import PluginDescriptor


def agent_loop_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="agent-loop",
        version="1.0.0",
        module="langharmess_core.plugins.loop.agent_loop",
        factory="agent-loop-factory",
        instance="agent-loop",
        specification=SPEC_AGENT_LOOP,
    )


def runtime_llm_descriptor(properties: dict[str, Any]) -> PluginDescriptor:
    """Describe the per-request LLM plugin installed at runtime."""
    return PluginDescriptor(
        name="runtime-llm",
        version="1.0.0",
        module="langharmess_core.plugins.llm.llm",
        factory="llm-plugin-factory",
        instance="runtime-llm",
        specification=SPEC_LLM,
        ranking=1000,
        properties=properties,
    )


def sqlite_checkpointer_descriptor(directory: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="sqlite-checkpointer",
        version="1.0.0",
        module="langharmess_core.plugins.checkpointer.sqlite",
        factory="sqlite-checkpointer-plugin-factory",
        instance="sqlite-checkpointer",
        specification=SPEC_CHECKPOINTER,
        properties={
            "plugin.checkpoint.path": str(
                Path(directory) / "langharmess_checkpoints.sqlite3"
            )
        },
    )


def session_index_descriptor(directory: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="session-index",
        version="1.0.0",
        module="langharmess_core.plugins.sessions.sqlite",
        factory="session-index-plugin-factory",
        instance="session-index",
        specification=SPEC_SESSION_INDEX,
        properties={"plugin.sessions.path": str(Path(directory) / "sessions.sqlite3")},
    )


def agent_registry_descriptor(directory: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="agent-registry",
        version="1.0.0",
        module="langharmess_core.plugins.agents.registry",
        factory="agent-registry-plugin-factory",
        instance="agent-registry",
        specification=SPEC_AGENT_REGISTRY,
        properties={"plugin.agents.path": str(Path(directory) / "agents.json")},
    )


def workspace_tools_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="workspace-tools",
        version="1.0.0",
        module="langharmess_core.plugins.tools.workspace",
        factory="workspace-tools-plugin-factory",
        instance="workspace-tools",
        specification=SPEC_TOOL,
        properties={"plugin.tools.root_dir": "."},
    )
