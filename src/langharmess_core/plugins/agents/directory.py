"""Agent directory plugin: one plugin set per agent."""

from __future__ import annotations

import logging
from typing import Any

from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
    Validate,
)

from langharmess_core.common.ids import validate_id
from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    AgentDirectoryProvider,
    AgentRegistryProvider,
)
from langharmess_core.plugin import (
    AGENT_PLUGIN_CATALOG,
    DEFAULT_AGENT_PLUGINS,
    agent_filter,
    agent_loop_descriptor,
    agent_plugin_descriptor,
    agent_required_modules,
    agent_scoped_specifications,
)
from langharmess_plugin.contracts import ScopedPluginRegistrar
from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.validation import ContractGuard
from langharmess_scope import ScopeId

LOGGER = logging.getLogger("langharmess.agent")


@ComponentFactory("agent-directory-plugin-factory")
@Provides(AgentDirectoryProvider)
@Property("_plugin_name", "plugin.name", "agent-directory")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_registry", AgentRegistryProvider, optional=True, immediate_rebind=True)
@RequiresBest("_scope", ScopedPluginRegistrar, optional=True, immediate_rebind=True)
class AgentDirectoryPlugin:
    """Materializes and resolves the plugin instances of every agent."""

    def __init__(self) -> None:
        self._plugin_name = "agent-directory"
        self._plugin_version = "1.0.0"
        self._registry: Any = None
        self._scope: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_registry": ContractGuard(self, "_registry", AgentRegistryProvider),
            "_scope": ContractGuard(self, "_scope", ScopedPluginRegistrar),
        }
        self._instances: dict[str, dict[str, PluginDescriptor]] = {}
        self._loops: dict[str, PluginDescriptor] = {}
        self._failed: set[str] = set()
        self._configs: dict[str, dict[str, Any]] = {}

    @Validate
    def _validate(self, bundle_context: Any) -> None:
        self._materialize_all()

    @BindField("_registry", if_valid=True)
    def _on_registry_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guards[field].admit(service):
            return
        self._materialize_all()

    @UnbindField("_registry")
    def _on_registry_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    @BindField("_scope", if_valid=True)
    def _on_scope_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guards[field].admit(service):
            return
        self._materialize_all()

    @UnbindField("_scope")
    def _on_scope_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)
        self._instances.clear()
        self._loops.clear()

    def list_agents(self) -> list[dict[str, Any]]:
        if self._registry is None:
            return []
        self._materialize_all()
        agents: list[dict[str, Any]] = []
        for agent in self._registry.list_agents():
            entry = dict(agent)
            plugins = self._instances.get(agent["id"], {})
            entry["materialized"] = agent["id"] in self._instances
            entry["plugins"] = sorted(plugins)
            agents.append(entry)
        return agents

    def get_loop(self, agent_id: str) -> Any | None:
        try:
            wanted = validate_id(agent_id, field="agent_id")
        except ValueError:
            return None
        self._materialize_all()
        if self._scope is None or wanted not in self._instances:
            return None
        return self._scope.find_service(SPEC_AGENT_LOOP, filter=agent_filter(wanted))

    def binding_properties(self, agent_id: str, plugin: str) -> dict[str, Any]:
        """Stored properties of one agent binding, empty when unconfigured."""
        stored = self._configs.get(agent_id, {}).get(plugin, {})
        properties = stored.get("properties")
        return dict(properties) if isinstance(properties, dict) else {}

    def apply_agent_config(self, agent_id: str, plugins: dict[str, Any]) -> None:
        """Replace one agent's plugin bindings with the given configuration."""
        wanted = validate_id(agent_id, field="agent_id")
        self._configs[wanted] = {
            str(name): dict(entry) for name, entry in plugins.items()
        }
        self._failed.discard(wanted)
        self._teardown(wanted)
        agent = self._lookup(wanted)
        if agent is not None and agent.get("enabled", False):
            self._materialize(agent)

    def remove_agent(self, agent_id: str) -> None:
        """Tear down one agent's plugin set and forget its configuration."""
        wanted = validate_id(agent_id, field="agent_id")
        self._configs.pop(wanted, None)
        self._failed.discard(wanted)
        self._teardown(wanted)
        if self._scope is not None:
            try:
                self._scope.remove_scope(ScopeId(wanted))
            except KeyError:
                LOGGER.debug("Scope %s was already gone", wanted)

    def ensure_plugin_instance(
        self, agent_id: str, plugin: str, properties: dict[str, Any]
    ) -> None:
        agent = self._require_agent(agent_id)
        self._materialize_all()
        if plugin not in AGENT_PLUGIN_CATALOG:
            raise ValueError(f"Unknown agent plugin: {plugin}")
        merged = {**self.binding_properties(agent["id"], plugin), **properties}
        descriptor = agent_plugin_descriptor(agent["id"], plugin, merged)
        current = self._instances.get(agent["id"], {}).get(plugin)
        if current == descriptor:
            return
        if current is not None:
            self._safe_kill(current.instance)
        scope_id = ScopeId(agent["id"])
        self._scope.instantiate_instance(
            descriptor, scope_id=scope_id, plugin_key=plugin
        )
        self._instances.setdefault(agent["id"], {})[plugin] = descriptor

    def reload(self, agent_id: str | None = None) -> None:
        targets = [agent_id] if agent_id is not None else list(self._instances)
        for target in targets:
            self._failed.discard(target)
            self._teardown(target)
            if agent_id is not None:
                agent = self._lookup(target)
                if agent is not None and agent.get("enabled", False):
                    self._materialize(agent)
        if agent_id is None:
            self._materialize_all()

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def _materialize_all(self) -> None:
        if self._registry is None or self._scope is None:
            return
        for agent in self._registry.list_agents():
            agent_id = agent["id"]
            if not agent.get("enabled", False):
                continue
            if agent_id in self._instances or agent_id in self._failed:
                continue
            self._materialize(agent)

    def _bindings(self, agent_id: str) -> dict[str, dict[str, Any]]:
        stored = self._configs.get(agent_id)
        if stored is None:
            return {plugin: {"enabled": True} for plugin in DEFAULT_AGENT_PLUGINS}
        return {
            name: dict(entry)
            for name, entry in stored.items()
            if entry.get("enabled", True)
        }

    def _materialize(self, agent: dict[str, Any]) -> None:
        agent_id = agent["id"]
        if self._scope is None:
            return
        missing = [
            module
            for module in agent_required_modules()
            if module not in self._scope.installed_modules()
        ]
        if missing:
            LOGGER.debug("Agent %s waits for bundles: %s", agent_id, missing)
            return
        created: dict[str, PluginDescriptor] = {}
        try:
            scope_id = ScopeId(agent_id)
            self._scope.ensure_scope(scope_id, name=agent.get("name") or agent_id)
            for plugin in self._bindings(agent_id):
                if plugin not in AGENT_PLUGIN_CATALOG:
                    LOGGER.warning(
                        "Ignoring unknown agent plugin %s for %s", plugin, agent_id
                    )
                    continue
                descriptor = self._binding_descriptor(agent, plugin)
                self._scope.instantiate_instance(
                    descriptor, scope_id=scope_id, plugin_key=plugin
                )
                created[plugin] = descriptor
            loop = agent_loop_descriptor(
                agent_id,
                agent_scoped_specifications(),
                visibility_filter=self._scope.scope_filter(scope_id),
            )
            self._scope.instantiate_instance(
                loop, scope_id=scope_id, plugin_key="agent-loop"
            )
        except Exception as exc:
            LOGGER.warning("Could not materialize agent %s: %s", agent_id, exc)
            for descriptor in created.values():
                self._safe_kill(descriptor.instance)
            try:
                self._scope.remove_scope(ScopeId(agent_id))
            except (KeyError, ValueError):
                LOGGER.debug("Could not roll back scope %s", agent_id)
            self._failed.add(agent_id)
            return
        self._failed.discard(agent_id)
        self._loops[agent_id] = loop
        self._instances[agent_id] = created

    def _binding_descriptor(
        self, agent: dict[str, Any], plugin: str
    ) -> PluginDescriptor:
        properties = dict(self.binding_properties(agent["id"], plugin))
        if plugin == "name":
            properties.setdefault("plugin.agent_name", agent.get("name") or agent["id"])
        return agent_plugin_descriptor(agent["id"], plugin, properties)

    def _teardown(self, agent_id: str) -> None:
        loop = self._loops.pop(agent_id, None)
        if loop is not None:
            self._safe_kill(loop.instance)
        for descriptor in self._instances.pop(agent_id, {}).values():
            self._safe_kill(descriptor.instance)

    def _safe_kill(self, instance: str) -> None:
        if self._scope is None:
            return
        try:
            self._scope.kill_instance(instance)
        except KeyError:
            LOGGER.debug("Scoped instance %s was already gone", instance)

    def _require_agent(self, agent_id: str) -> dict[str, Any]:
        wanted = validate_id(agent_id, field="agent_id")
        if self._registry is None or self._scope is None:
            raise RuntimeError("Agent directory dependencies are unavailable")
        agent = self._registry.get_agent(wanted)
        if agent is None:
            raise ValueError(f"Unknown agent: {wanted}")
        if not agent.get("enabled", False):
            raise ValueError(f"Agent is disabled: {wanted}")
        return dict(agent)

    def _lookup(self, agent_id: str) -> dict[str, Any] | None:
        if self._registry is None:
            return None
        try:
            wanted = validate_id(agent_id, field="agent_id")
        except ValueError:
            return None
        found = self._registry.get_agent(wanted)
        return dict(found) if found is not None else None
