"""Descriptors and assembly helpers for the built-in core plugins."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from langharmess_core.contracts import (
    SPEC_AGENT_DIRECTORY,
    SPEC_AGENT_LOOP,
    SPEC_AGENT_REGISTRY,
    SPEC_AGENT_SERVER,
    SPEC_CACHE,
    SPEC_CHECKPOINTER,
    SPEC_CONTEXT_SCHEMA,
    SPEC_DEBUG,
    SPEC_INTERRUPT_AFTER,
    SPEC_INTERRUPT_BEFORE,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_NAME,
    SPEC_RESPONSE_FORMAT,
    SPEC_SESSION_INDEX,
    SPEC_STATE_SCHEMA,
    SPEC_STORE,
    SPEC_SYSTEM_PROMPT,
    SPEC_TOOL,
    SPEC_TRANSFORMERS,
)
from langharmess_core.plugins.agents.export import AGENT_TOOL_EXPORTS
from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
from langharmess_plugin.package import PluginContribution, PluginPackage
from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.scope_const import AGENT_SCOPE_ID, agent_instance_scope_id

AGENT_PLUGIN_CATALOG: dict[str, tuple[str, str, str]] = {
    "llm": (
        "langharmess_core.plugins.llm.llm",
        "llm-plugin-factory",
        SPEC_LLM,
    ),
    "tools": (
        "langharmess_core.plugins.tools.workspace",
        "workspace-tools-plugin-factory",
        SPEC_TOOL,
    ),
    "name": (
        "langharmess_core.plugins.name.template_name",
        "agent-name-plugin-factory",
        SPEC_NAME,
    ),
}

DEFAULT_AGENT_PLUGINS: tuple[str, ...] = ("tools", "name")

DYNAMIC_PLUGIN_CATALOG: dict[str, tuple[str, str, str]] = {
    "cache-plugin": (
        "langharmess_core.plugins.cache.template_cache",
        "cache-plugin-factory",
        SPEC_CACHE,
    ),
    "checkpointer-plugin": (
        "langharmess_core.plugins.checkpointer.template_checkpointer",
        "checkpointer-plugin-factory",
        SPEC_CHECKPOINTER,
    ),
    "context-schema-plugin": (
        "langharmess_core.plugins.context_schema.template_context_schema",
        "context-schema-plugin-factory",
        SPEC_CONTEXT_SCHEMA,
    ),
    "debug-plugin": (
        "langharmess_core.plugins.debug.template_debug",
        "debug-plugin-factory",
        SPEC_DEBUG,
    ),
    "interrupt-after-plugin": (
        "langharmess_core.plugins.interrupt_after.template_interrupt_after",
        "interrupt-after-plugin-factory",
        SPEC_INTERRUPT_AFTER,
    ),
    "interrupt-before-plugin": (
        "langharmess_core.plugins.interrupt_before.template_interrupt_before",
        "interrupt-before-plugin-factory",
        SPEC_INTERRUPT_BEFORE,
    ),
    "management-tools-plugin": (
        "langharmess_core.plugins.tools.management",
        "management-tools-plugin-factory",
        SPEC_TOOL,
    ),
    "middleware-plugin": (
        "langharmess_core.plugins.middleware.template_middleware",
        "middleware-plugin-factory",
        SPEC_MIDDLEWARE,
    ),
    "response-format-plugin": (
        "langharmess_core.plugins.response_format.template_response_format",
        "response-format-plugin-factory",
        SPEC_RESPONSE_FORMAT,
    ),
    "state-schema-plugin": (
        "langharmess_core.plugins.state_schema.template_state_schema",
        "state-schema-plugin-factory",
        SPEC_STATE_SCHEMA,
    ),
    "store-plugin": (
        "langharmess_core.plugins.store.template_store",
        "store-plugin-factory",
        SPEC_STORE,
    ),
    "system-prompt-plugin": (
        "langharmess_core.plugins.system_prompt.template_system_prompt",
        "system-prompt-plugin-factory",
        SPEC_SYSTEM_PROMPT,
    ),
    "tools-plugin": (
        "langharmess_core.plugins.tools.tools",
        "tools-plugin-factory",
        SPEC_TOOL,
    ),
    "transformers-plugin": (
        "langharmess_core.plugins.transformers.template_transformers",
        "transformers-plugin-factory",
        SPEC_TRANSFORMERS,
    ),
}

AGENT_LOOP_MODULE = "langharmess_core.plugins.loop.agent_loop"
TOOL_EXPORT_ADAPTER_MODULE = "langharmess_core.plugins.tools.export_adapter"

AGENT_PLUGIN_SETTINGS: dict[str, dict[str, Any]] = {
    "tools": {"plugin.tools.root_dir": "."},
}

AGENT_LOOP_FIELDS: dict[str, str] = {
    SPEC_LLM: "_llm_provider",
    SPEC_TOOL: "_tool_providers",
    SPEC_SYSTEM_PROMPT: "_system_prompt_providers",
    SPEC_MIDDLEWARE: "_middleware_providers",
    SPEC_NAME: "_name_provider",
    SPEC_RESPONSE_FORMAT: "_response_format_provider",
    SPEC_CACHE: "_cache_provider",
    SPEC_TRANSFORMERS: "_transformers_providers",
    SPEC_INTERRUPT_BEFORE: "_interrupt_before_providers",
    SPEC_INTERRUPT_AFTER: "_interrupt_after_providers",
}


def agent_scoped_specifications() -> list[str]:
    """Every specification the directory may materialize per agent."""
    return list(dict.fromkeys(spec for _, _, spec in AGENT_PLUGIN_CATALOG.values()))


def agent_required_modules() -> list[str]:
    """Bundles the directory needs before it can materialize an agent."""
    modules = [AGENT_PLUGIN_CATALOG[plugin][0] for plugin in DEFAULT_AGENT_PLUGINS]
    modules.append(AGENT_LOOP_MODULE)
    return list(dict.fromkeys(modules))


def agent_filter(agent_id: str) -> str:
    """Build the LDAP filter selecting one agent's plugin instances."""
    return f"(plugin.agent_id={agent_id})"


def agent_plugin_descriptor(
    agent_id: str, plugin: str, properties: dict[str, Any] | None = None
) -> PluginDescriptor:
    """Describe one agent-scoped plugin instance from the catalog."""
    module, factory, specification = AGENT_PLUGIN_CATALOG[plugin]
    merged = dict(AGENT_PLUGIN_SETTINGS.get(plugin, {}))
    merged.update(properties or {})
    merged["plugin.agent_id"] = agent_id
    return PluginDescriptor(
        name=f"{plugin}@{agent_id}",
        version="1.0.0",
        module=module,
        factory=factory,
        instance=f"{plugin}@{agent_id}",
        specification=specification,
        properties=merged,
        scope=str(agent_instance_scope_id(agent_id)),
        scope_parent="agent",
    )


def agent_plugin_template_descriptor(plugin: str) -> PluginDescriptor:
    """Install a catalog bundle without instantiating it."""
    module, factory, specification = AGENT_PLUGIN_CATALOG[plugin]
    return PluginDescriptor(
        name=f"{plugin}-template",
        version="1.0.0",
        module=module,
        factory=factory,
        instance=f"{plugin}-template",
        specification=specification,
        enabled=False,
        scope="agent",
        scope_parent="root",
    )


def default_llm_descriptor(properties: dict[str, Any]) -> PluginDescriptor:
    """Describe the agent-scope fallback LLM seeded from providers.default.

    The instance carries no ``plugin.agent_id``, so it never matches an agent
    loop's ``_llm_provider`` filter; loops pick it up through the scoped
    ``_scoped_llm_providers`` visibility filter and an agent-specific LLM
    shadows it by nearest-scope selection.
    """
    module, factory, specification = AGENT_PLUGIN_CATALOG["llm"]
    return PluginDescriptor(
        name="llm@default",
        version="1.0.0",
        module=module,
        factory=factory,
        instance="llm@default",
        specification=specification,
        properties=properties,
        scope=str(AGENT_SCOPE_ID),
        scope_parent="root",
    )


def agent_loop_descriptor(
    agent_id: str,
    scoped_specifications: Iterable[str],
    *,
    visibility_filter: str | None = None,
) -> PluginDescriptor:
    """Describe the loop instance scoped to one agent's plugin set."""
    scoped_specifications = tuple(scoped_specifications)
    filters = {
        AGENT_LOOP_FIELDS[specification]: visibility_filter or agent_filter(agent_id)
        for specification in scoped_specifications
        if specification in AGENT_LOOP_FIELDS
    }
    if SPEC_LLM in scoped_specifications:
        filters["_scoped_llm_providers"] = visibility_filter or agent_filter(agent_id)
    return PluginDescriptor(
        name=f"agent-loop@{agent_id}",
        version="1.0.0",
        module=AGENT_LOOP_MODULE,
        factory="agent-loop-factory",
        instance=f"agent-loop@{agent_id}",
        specification=SPEC_AGENT_LOOP,
        properties={"plugin.agent_id": agent_id, "requires.filters": filters},
        scope=str(agent_instance_scope_id(agent_id)),
        scope_parent="agent",
    )


def agent_loop_template_descriptor() -> PluginDescriptor:
    """Install the loop bundle without instantiating it."""
    return PluginDescriptor(
        name="agent-loop-template",
        version="1.0.0",
        module=AGENT_LOOP_MODULE,
        factory="agent-loop-factory",
        instance="agent-loop-template",
        specification=SPEC_AGENT_LOOP,
        enabled=False,
        scope="agent",
        scope_parent="root",
    )


def tool_export_adapter_template_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="tool-export-adapter-template",
        version="1.0.0",
        module=TOOL_EXPORT_ADAPTER_MODULE,
        factory="tool-export-adapter-factory",
        instance="tool-export-adapter-template",
        specification=SPEC_TOOL,
        enabled=False,
        scope="agent",
        scope_parent="root",
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
        scope="server",
        scope_parent="root",
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
        scope="server",
        scope_parent="root",
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
        scope="server",
        scope_parent="root",
    )


def agent_directory_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="agent-directory",
        version="1.0.0",
        module="langharmess_core.plugins.agents.directory",
        factory="agent-directory-plugin-factory",
        instance="agent-directory",
        specification=SPEC_AGENT_DIRECTORY,
        scope="server",
        scope_parent="root",
    )


def agent_server_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="agent-server",
        version="1.0.0",
        module="langharmess_core.plugins.agents.server",
        factory="agent-server-factory",
        instance="agent-server",
        specification=SPEC_AGENT_SERVER,
        scope="server",
        scope_parent="root",
    )


def builtin_package() -> PluginPackage:
    """Describe server-scoped core plugins and agent plugin templates."""
    directory = str(Path.home() / ".langharmess")
    return PluginPackage(
        id="builtin.core",
        version="1.0.0",
        contributions=(
            PluginContribution(
                "sqlite-checkpointer",
                "server",
                sqlite_checkpointer_descriptor(directory),
            ),
            PluginContribution(
                "session-index", "server", session_index_descriptor(directory)
            ),
            PluginContribution(
                "agent-registry", "server", agent_registry_descriptor(directory)
            ),
            PluginContribution(
                "agent-directory", "server", agent_directory_descriptor()
            ),
            PluginContribution("agent-server", "server", agent_server_descriptor()),
            PluginContribution(
                "llm-template", "agent", agent_plugin_template_descriptor("llm")
            ),
            PluginContribution(
                "tools-template", "agent", agent_plugin_template_descriptor("tools")
            ),
            PluginContribution(
                "name-template", "agent", agent_plugin_template_descriptor("name")
            ),
            PluginContribution(
                "agent-loop-template", "agent", agent_loop_template_descriptor()
            ),
            PluginContribution(
                "tool-export-adapter-template",
                "agent",
                tool_export_adapter_template_descriptor(),
            ),
        ),
    )


def dynamic_template_descriptor(plugin: str) -> PluginDescriptor:
    """Install a dynamic bundle without instantiating it."""
    module, factory, specification = DYNAMIC_PLUGIN_CATALOG[plugin]
    return PluginDescriptor(
        name=f"{plugin}-template",
        version="1.0.0",
        module=module,
        factory=factory,
        instance=f"{plugin}-template",
        specification=specification,
        enabled=False,
        scope="agent",
        scope_parent="root",
    )


def dynamic_package() -> PluginPackage:
    """Describe the core plugins installable at runtime, beyond the built-in set."""
    contributions = [
        PluginContribution(
            f"{plugin}-template", "agent", dynamic_template_descriptor(plugin)
        )
        for plugin in DYNAMIC_PLUGIN_CATALOG
    ]
    contributions.append(
        PluginContribution(
            "management-tools-plugin-instance",
            "agent_instance",
            replace(
                dynamic_template_descriptor("management-tools-plugin"),
                name="management-tools-plugin-agent",
                instance="management-tools-plugin-agent",
            ),
        )
    )
    return PluginPackage(
        id="dynamic.core",
        version="1.0.0",
        contributions=tuple(contributions),
    )


def agent_tools_package() -> PluginPackage:
    """Describe the agent management tools installed via dynamic discovery."""
    return PluginPackage(
        id="agent.tools",
        version="1.0.0",
        contributions=(
            PluginContribution(
                "agent-operations",
                "agent",
                PluginDescriptor(
                    name="agent-operations-export",
                    version="1.0.0",
                    module="langharmess_core.plugins.agents.export",
                    factory="agent-operations-export-factory",
                    instance="agent-operations-export",
                    specification=SPEC_TOOL_EXPORT_TARGET,
                    scope="agent",
                    scope_parent="root",
                    enabled=True,
                ),
                tool_exports=AGENT_TOOL_EXPORTS,
            ),
        ),
    )
