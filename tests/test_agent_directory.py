"""Unit tests for the agent directory plugin (per-agent plugin sets)."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from typing import Any, cast

import pytest

from langharmess_core.contracts import (
    SPEC_AGENT_DIRECTORY,
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_NAME,
    SPEC_TOOL,
    AgentDirectoryProvider,
)
from langharmess_core.plugins.agents.directory import AgentDirectoryPlugin
from langharmess_plugin.contracts import SPEC_PLUGIN_SCOPE, ScopedPluginRegistrar
from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.validation import contract_for, validate


def agent_record(
    agent_id: str = "simple_agent", *, enabled: bool = True, name: str = "Simple Agent"
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": name,
        "description": f"{agent_id} description",
        "enabled": enabled,
        "created_at": "2026-09-15T00:00:00+00:00",
        "updated_at": "2026-09-15T00:00:00+00:00",
    }


REQUIRED_MODULES = {
    "langharmess_core.plugins.tools.workspace",
    "langharmess_core.plugins.name.template_name",
    "langharmess_core.plugins.loop.agent_loop",
}


class FakeScope:
    def __init__(
        self, *, fail_on: str | None = None, modules: set[str] | None = None
    ) -> None:
        self.instances: dict[str, PluginDescriptor] = {}
        self.killed: list[str] = []
        self.services: dict[tuple[str, str | None], Any] = {}
        self.fail_on = fail_on
        self.modules = REQUIRED_MODULES if modules is None else modules

    def installed_modules(self) -> set[str]:
        return set(self.modules)

    def instantiate_instance(self, descriptor: PluginDescriptor) -> None:
        if self.fail_on is not None and descriptor.instance == self.fail_on:
            raise ValueError(f"cannot instantiate {descriptor.instance}")
        if descriptor.instance in self.instances:
            raise ValueError(f"Instance {descriptor.instance!r} is already instantiated")
        self.instances[descriptor.instance] = descriptor

    def kill_instance(self, instance: str) -> None:
        if instance not in self.instances:
            raise KeyError(instance)
        self.instances.pop(instance)
        self.killed.append(instance)

    def find_service(self, specification: str, filter: str | None = None) -> Any:
        return self.services.get((specification, filter))

    def apply_config(self, overrides: dict[str, Any]) -> dict[str, list[str]]:
        return {"applied": sorted(overrides), "restart_required": []}


class FakeRegistry:
    def __init__(self, agents: list[dict[str, Any]] | None = None) -> None:
        self._agents = agents if agents is not None else [agent_record()]

    def list_agents(self) -> list[dict[str, Any]]:
        return [dict(agent) for agent in self._agents]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        for agent in self._agents:
            if agent["id"] == agent_id:
                return dict(agent)
        return None

    def create_agent(
        self, agent_id: str, name: str, description: str
    ) -> dict[str, Any]:
        return agent_record(agent_id, name=name)

    def update_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        return agent_record(agent_id)

    def delete_agent(self, agent_id: str) -> None:
        return None


def make_directory(
    agents: list[dict[str, Any]] | None = None, scope: FakeScope | None = None
) -> AgentDirectoryPlugin:
    plugin = AgentDirectoryPlugin()
    plugin._registry = FakeRegistry(agents)
    plugin._scope = scope if scope is not None else FakeScope()
    plugin._validate(cast(Any, None))
    return plugin


def test_directory_contract_is_pinned() -> None:
    assert SPEC_AGENT_DIRECTORY == "agent.directory"
    assert contract_for(SPEC_AGENT_DIRECTORY) is AgentDirectoryProvider
    assert validate(AgentDirectoryPlugin(), AgentDirectoryProvider) == ()
    assert contract_for(SPEC_PLUGIN_SCOPE) is ScopedPluginRegistrar


def test_validate_materializes_default_plugins_and_loop() -> None:
    plugin = make_directory()
    instances = plugin._scope.instances

    assert set(instances) == {
        "tools@simple_agent",
        "name@simple_agent",
        "agent-loop@simple_agent",
    }
    tools = instances["tools@simple_agent"]
    assert tools.module == "langharmess_core.plugins.tools.workspace"
    assert tools.specification == SPEC_TOOL
    assert tools.properties["plugin.agent_id"] == "simple_agent"
    assert tools.properties["plugin.tools.root_dir"] == "."

    name = instances["name@simple_agent"]
    assert name.specification == SPEC_NAME
    assert name.properties["plugin.agent_name"] == "Simple Agent"

    loop = instances["agent-loop@simple_agent"]
    assert loop.specification == SPEC_AGENT_LOOP
    assert loop.properties["plugin.agent_id"] == "simple_agent"
    assert loop.properties["requires.filters"] == {
        "_llm_provider": "(plugin.agent_id=simple_agent)",
        "_tool_providers": "(plugin.agent_id=simple_agent)",
        "_name_provider": "(plugin.agent_id=simple_agent)",
    }


def test_validate_skips_disabled_agents() -> None:
    plugin = make_directory([agent_record(enabled=False)])
    assert plugin._scope.instances == {}
    assert plugin.list_agents()[0]["materialized"] is False


def test_validate_without_dependencies_is_a_noop() -> None:
    plugin = AgentDirectoryPlugin()
    plugin._validate(cast(Any, None))
    assert plugin.list_agents() == []
    assert plugin.get_loop("simple_agent") is None


def test_list_agents_reports_materialization() -> None:
    plugin = make_directory()
    entry = plugin.list_agents()[0]
    assert entry["id"] == "simple_agent"
    assert entry["materialized"] is True
    assert entry["plugins"] == ["name", "tools"]


def test_get_loop_uses_the_agent_filter() -> None:
    plugin = make_directory()
    plugin._scope.services[(SPEC_AGENT_LOOP, "(plugin.agent_id=simple_agent)")] = "loop"

    assert plugin.get_loop("simple_agent") == "loop"
    assert plugin.get_loop("missing_agent") is None
    assert plugin.get_loop("bad agent") is None


def test_ensure_plugin_instance_creates_agent_scoped_llm() -> None:
    plugin = make_directory()
    properties = {
        "plugin.model.name": "test-model",
        "plugin.model.api_key": "key",
        "plugin.model.base_url": "https://models.example/v1",
        "plugin.model.protocol": "chat",
    }

    plugin.ensure_plugin_instance("simple_agent", "llm", properties)

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.module == "langharmess_core.plugins.llm.llm"
    assert descriptor.specification == SPEC_LLM
    assert descriptor.properties == {**properties, "plugin.agent_id": "simple_agent"}
    assert plugin.list_agents()[0]["plugins"] == ["llm", "name", "tools"]


def test_ensure_plugin_instance_is_idempotent_for_equal_configuration() -> None:
    plugin = make_directory()
    properties = {"plugin.model.name": "test-model"}

    plugin.ensure_plugin_instance("simple_agent", "llm", properties)
    plugin.ensure_plugin_instance("simple_agent", "llm", dict(properties))

    assert plugin._scope.killed == []
    assert sorted(plugin._scope.instances) == [
        "agent-loop@simple_agent",
        "llm@simple_agent",
        "name@simple_agent",
        "tools@simple_agent",
    ]


def test_ensure_plugin_instance_replaces_changed_configuration() -> None:
    plugin = make_directory()
    plugin.ensure_plugin_instance("simple_agent", "llm", {"plugin.model.name": "one"})
    plugin.ensure_plugin_instance("simple_agent", "llm", {"plugin.model.name": "two"})

    assert plugin._scope.killed == ["llm@simple_agent"]
    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties["plugin.model.name"] == "two"


def test_ensure_plugin_instance_rejects_unknown_agent() -> None:
    plugin = make_directory()
    with pytest.raises(ValueError, match="Unknown agent: ghost"):
        plugin.ensure_plugin_instance("ghost", "llm", {})


def test_ensure_plugin_instance_rejects_disabled_agent() -> None:
    plugin = make_directory([agent_record(enabled=False)])
    with pytest.raises(ValueError, match="Agent is disabled"):
        plugin.ensure_plugin_instance("simple_agent", "llm", {})


def test_ensure_plugin_instance_rejects_unknown_plugin() -> None:
    plugin = make_directory()
    with pytest.raises(ValueError, match="Unknown agent plugin: warp"):
        plugin.ensure_plugin_instance("simple_agent", "warp", {})


def test_reload_tears_down_and_materializes_again() -> None:
    plugin = make_directory()
    plugin.ensure_plugin_instance("simple_agent", "llm", {"plugin.model.name": "one"})

    plugin.reload("simple_agent")

    assert "agent-loop@simple_agent" in plugin._scope.killed
    assert "tools@simple_agent" in plugin._scope.killed
    assert "llm@simple_agent" in plugin._scope.killed
    assert set(plugin._scope.instances) == {
        "tools@simple_agent",
        "name@simple_agent",
        "agent-loop@simple_agent",
    }
    assert plugin.list_agents()[0]["plugins"] == ["name", "tools"]


def test_reload_without_agent_targets_every_materialized_agent() -> None:
    plugin = make_directory([agent_record("a1"), agent_record("a2")])
    plugin.reload()

    assert "agent-loop@a1" in plugin._scope.killed
    assert "agent-loop@a2" in plugin._scope.killed
    assert set(plugin._scope.instances) == {
        "tools@a1",
        "name@a1",
        "agent-loop@a1",
        "tools@a2",
        "name@a2",
        "agent-loop@a2",
    }


def test_materialization_failure_is_contained() -> None:
    scope = FakeScope(fail_on="name@simple_agent")
    plugin = make_directory(scope=scope)

    assert plugin.list_agents()[0]["materialized"] is False
    assert "tools@simple_agent" in scope.killed
    assert plugin._scope.instances == {}


def test_bind_callbacks_materialize_and_release() -> None:
    plugin = AgentDirectoryPlugin()
    plugin._registry = FakeRegistry()
    plugin._scope = FakeScope()

    plugin._on_scope_bind("_scope", plugin._scope, None)
    assert "tools@simple_agent" in plugin._scope.instances

    plugin._on_scope_unbind("_scope", plugin._scope, None)
    assert plugin._instances == {}
    assert plugin._loops == {}
    assert plugin.list_agents()[0]["materialized"] is False


def test_apply_agent_config_honours_stored_bindings() -> None:
    plugin = make_directory()

    plugin.apply_agent_config(
        "simple_agent",
        {"tools": {"enabled": True, "properties": {"plugin.tools.root_dir": "/work"}}},
    )

    assert set(plugin._scope.instances) == {"tools@simple_agent", "agent-loop@simple_agent"}
    tools = plugin._scope.instances["tools@simple_agent"]
    assert tools.properties["plugin.tools.root_dir"] == "/work"
    assert plugin.list_agents()[0]["plugins"] == ["tools"]
    assert "name@simple_agent" in plugin._scope.killed


def test_apply_agent_config_skips_disabled_bindings() -> None:
    plugin = make_directory()
    plugin.apply_agent_config(
        "simple_agent",
        {
            "tools": {"enabled": False},
            "name": {"enabled": True, "properties": {"plugin.agent_name": "Custom"}},
        },
    )
    assert set(plugin._scope.instances) == {"name@simple_agent", "agent-loop@simple_agent"}
    assert (
        plugin._scope.instances["name@simple_agent"].properties["plugin.agent_name"]
        == "Custom"
    )


def test_apply_agent_config_ignores_unknown_plugins() -> None:
    plugin = make_directory()
    plugin.apply_agent_config("simple_agent", {"warp": {"enabled": True}})
    assert set(plugin._scope.instances) == {"agent-loop@simple_agent"}
    assert plugin.list_agents()[0]["plugins"] == []


def test_ensure_plugin_instance_merges_stored_binding_properties() -> None:
    plugin = make_directory()
    plugin.apply_agent_config(
        "simple_agent",
        {"llm": {"properties": {"plugin.model.name": "stored-model"}}},
    )

    plugin.ensure_plugin_instance("simple_agent", "llm", {})

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties["plugin.model.name"] == "stored-model"
    assert plugin.binding_properties("simple_agent", "llm") == {
        "plugin.model.name": "stored-model"
    }


def test_ensure_plugin_instance_request_overrides_stored_defaults() -> None:
    plugin = make_directory()
    plugin.apply_agent_config(
        "simple_agent",
        {"llm": {"properties": {"plugin.model.name": "stored", "plugin.model.base_url": "u"}}},
    )

    plugin.ensure_plugin_instance("simple_agent", "llm", {"plugin.model.name": "asked"})

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties == {
        "plugin.model.name": "asked",
        "plugin.model.base_url": "u",
        "plugin.agent_id": "simple_agent",
    }


def test_binding_properties_empty_for_unconfigured_agent() -> None:
    plugin = make_directory()
    assert plugin.binding_properties("simple_agent", "llm") == {}


def test_remove_agent_tears_down_instances() -> None:
    plugin = make_directory()
    plugin.ensure_plugin_instance("simple_agent", "llm", {"plugin.model.name": "m"})

    plugin.remove_agent("simple_agent")

    assert plugin._scope.instances == {}
    assert "agent-loop@simple_agent" in plugin._scope.killed
    assert plugin.get_loop("simple_agent") is None
    assert plugin._configs == {}


def test_plugin_info_and_reload_without_materialization() -> None:
    plugin = make_directory([agent_record(enabled=False)])
    assert plugin.get_plugin_info() == {
        "name": "agent-directory",
        "version": "1.0.0",
    }
    plugin.reload()
    assert plugin._scope.instances == {}


def test_ensure_plugin_instance_without_scope_raises() -> None:
    plugin = AgentDirectoryPlugin()
    plugin._registry = FakeRegistry()
    with pytest.raises(RuntimeError, match="dependencies"):
        plugin.ensure_plugin_instance("simple_agent", "llm", {})


def test_bind_and_unbind_callbacks_guard_services() -> None:
    plugin = AgentDirectoryPlugin()
    registry = FakeRegistry()
    scope = FakeScope()
    plugin._registry = registry
    plugin._scope = scope

    plugin._on_registry_bind("_registry", registry, None)
    plugin._on_scope_bind("_scope", scope, None)
    assert "agent-loop@simple_agent" in scope.instances

    plugin._on_registry_unbind("_registry", registry, None)
    plugin._on_scope_unbind("_scope", scope, None)
    assert plugin._instances == {}


def test_remove_agent_without_configuration_is_safe() -> None:
    plugin = make_directory()
    plugin.remove_agent("simple_agent")
    plugin.remove_agent("unmaterialized_agent")
    assert plugin._scope.instances == {}


def test_reload_of_unknown_agent_is_a_noop() -> None:
    plugin = make_directory()
    plugin.reload("ghost")
    assert set(plugin._scope.instances) == {
        "tools@simple_agent",
        "name@simple_agent",
        "agent-loop@simple_agent",
    }
