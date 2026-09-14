"""Descriptors and assembly helpers for the built-in core plugins."""

from __future__ import annotations

from typing import Any

from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_CHECKPOINTER,
    SPEC_LLM,
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


def sqlite_checkpointer_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="sqlite-checkpointer",
        version="1.0.0",
        module="langharmess_core.plugins.checkpointer.sqlite",
        factory="sqlite-checkpointer-plugin-factory",
        instance="sqlite-checkpointer",
        specification=SPEC_CHECKPOINTER,
        properties={"plugin.checkpoint.path": "langharmess_checkpoints.sqlite3"},
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
