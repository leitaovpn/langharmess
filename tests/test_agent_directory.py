"""Unit tests for the agent directory plugin (per-agent plugin sets)."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

import logging
from typing import Any, cast

import pytest

from langharness_core.contracts import (
    SPEC_AGENT_DIRECTORY,
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_NAME,
    SPEC_TOOL,
    AgentDirectoryProvider,
)
from langharness_core.plugins.agents.directory import AgentDirectoryPlugin
from langharness_plugin.contracts import SPEC_PLUGIN_SCOPE, ScopedPluginRegistrar
from langharness_plugin.registry import PluginDescriptor
from langharness_plugin.scope_const import AGENT_SCOPE_ID
from langharness_plugin.validation import contract_for, validate
from langharness_scope import ScopeId, ScopeTree


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
    "langharness_core.plugins.tools.workspace",
    "langharness_core.plugins.name.template_name",
    "langharness_core.plugins.loop.agent_loop",
}

LLM_MODULE = "langharness_core.plugins.llm.llm"

# The default fake has every module installed; tests that exercise the
# wait-for-bundles path remove modules from this set explicitly.
INSTALLED_MODULES = REQUIRED_MODULES | {LLM_MODULE}


class FakeScope:
    def __init__(
        self, *, fail_on: str | None = None, modules: set[str] | None = None
    ) -> None:
        self.instances: dict[str, PluginDescriptor] = {}
        self.instance_scopes: dict[str, str] = {}
        self.killed: list[str] = []
        self.services: dict[tuple[str, str | None], Any] = {}
        self.fail_on = fail_on
        self.modules = INSTALLED_MODULES if modules is None else modules
        self.tree = ScopeTree()

    def installed_modules(self) -> set[str]:
        return set(self.modules)

    def instantiate_instance(
        self,
        descriptor: PluginDescriptor,
        *,
        scope_id: ScopeId | None = None,
        plugin_key: str | None = None,
    ) -> None:
        if self.fail_on is not None and descriptor.instance == self.fail_on:
            raise ValueError(f"cannot instantiate {descriptor.instance}")
        if descriptor.instance in self.instances:
            raise ValueError(
                f"Instance {descriptor.instance!r} is already instantiated"
            )
        self.instances[descriptor.instance] = descriptor
        if scope_id is not None:
            self.instance_scopes[descriptor.instance] = str(scope_id)

    def ensure_scope(
        self,
        scope_id: ScopeId,
        *,
        name: str,
        parent_id: ScopeId | None = None,
    ) -> None:
        if self.tree.get(scope_id) is None:
            wanted_parent = parent_id or ScopeId("root")
            if self.tree.get(wanted_parent) is None:
                self.tree.create(wanted_parent, str(wanted_parent))
            self.tree.create(scope_id, name, wanted_parent)

    def scope_filter(self, scope_id: ScopeId) -> str:
        visible = self.tree.ancestors(scope_id, include_self=True)
        return "(|" + "".join(
            f"(plugin.scope_id={scope.id})" for scope in visible
        ) + ")"

    def remove_scope(self, scope_id: ScopeId, *, recursive: bool = False) -> None:
        self.tree.remove(scope_id, recursive=recursive)

    def kill_instance(self, instance: str) -> None:
        if instance not in self.instances:
            raise KeyError(instance)
        self.instances.pop(instance)
        self.killed.append(instance)

    def find_service(self, specification: str, filter: str | None = None) -> Any:
        return self.services.get((specification, filter))

    def find_services(
        self, specification: str, filter: str | None = None
    ) -> list[Any]:
        service = self.find_service(specification, filter)
        return [] if service is None else [service]

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


class FakeConfigs:
    """Minimal Configs service stub; missing default raises like the real one."""

    def __init__(self, default: dict[str, Any] | None = None) -> None:
        self._default = default

    def get(self, section: str, key: str, fallback: str | None = None) -> str | None:
        return fallback

    def get_section(self, section: str) -> dict[str, Any]:
        return {}

    def get_provider(self, name: str) -> dict[str, Any]:
        return {}

    def list_providers(self) -> list[str]:
        return []

    def get_default_provider(self) -> dict[str, Any]:
        if self._default is None:
            raise ValueError(
                "No default model is configured: add a "
                "[providers.default] section to langharness.toml"
            )
        return dict(self._default)


def make_directory(
    agents: list[dict[str, Any]] | None = None,
    scope: FakeScope | None = None,
    configs: FakeConfigs | None = None,
) -> AgentDirectoryPlugin:
    plugin = AgentDirectoryPlugin()
    plugin._registry = FakeRegistry(agents)
    plugin._scope = scope if scope is not None else FakeScope()
    if configs is not None:
        plugin._configs_service = configs
        plugin._on_configs_service_bind("_configs_service", configs, None)
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
    assert tools.module == "langharness_core.plugins.tools.workspace"
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
        "_llm_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_scoped_llm_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_tool_providers": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
        "_name_provider": "(|(plugin.scope_id=agent:simple_agent)(plugin.scope_id=agent)(plugin.scope_id=root))",
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
    assert descriptor.module == "langharness_core.plugins.llm.llm"
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


def test_remove_agent_removes_its_scope_after_instances() -> None:
    plugin = make_directory()

    plugin.remove_agent("simple_agent")

    assert plugin._scope.tree.get(ScopeId("agent:simple_agent")) is None
    assert plugin._scope.instances == {}


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


def test_materialize_creates_agent_scope_default_llm_from_providers_default() -> None:
    plugin = make_directory(
        configs=FakeConfigs(
            {
                "model": "default-model",
                "api_key": "default-key",
                "base_url": "https://default.example/v1",
                "protocol": "responses",
            }
        )
    )

    default = plugin._scope.instances["llm@default"]
    assert default.module == "langharness_core.plugins.llm.llm"
    assert default.specification == SPEC_LLM
    assert default.properties == {
        "plugin.model.name": "default-model",
        "plugin.model.api_key": "default-key",
        "plugin.model.base_url": "https://default.example/v1",
        "plugin.model.protocol": "responses",
    }
    assert "plugin.agent_id" not in default.properties
    assert plugin._scope.instance_scopes["llm@default"] == str(AGENT_SCOPE_ID)


def test_default_llm_skipped_without_configs_service() -> None:
    plugin = make_directory()
    assert "llm@default" not in plugin._scope.instances


def test_default_llm_skipped_when_providers_default_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        plugin = make_directory(configs=FakeConfigs(None))

    assert "llm@default" not in plugin._scope.instances
    assert "Default model unavailable" in caplog.text


def test_default_llm_created_once_across_repeated_materialization() -> None:
    plugin = make_directory(configs=FakeConfigs({"model": "default-model"}))

    plugin._materialize_all()
    plugin._materialize_all()

    assert list(plugin._scope.instances).count("llm@default") == 1


def test_late_configs_bind_creates_default_llm() -> None:
    plugin = make_directory()
    assert "llm@default" not in plugin._scope.instances

    late_configs = FakeConfigs({"model": "late-model"})
    plugin._configs_service = late_configs
    plugin._on_configs_service_bind("_configs_service", late_configs, None)

    default = plugin._scope.instances["llm@default"]
    assert default.properties["plugin.model.name"] == "late-model"


def test_agent_specific_llm_coexists_with_agent_scope_default() -> None:
    plugin = make_directory(configs=FakeConfigs({"model": "default-model"}))

    plugin.ensure_plugin_instance(
        "simple_agent", "llm", {"plugin.model.name": "agent-model"}
    )

    own = plugin._scope.instances["llm@simple_agent"]
    assert own.properties["plugin.agent_id"] == "simple_agent"
    assert own.properties["plugin.model.name"] == "agent-model"
    assert "llm@default" in plugin._scope.instances


DEFAULT_PROVIDER = {
    "model": "default-model",
    "api_key": "default-key",
    "base_url": "https://default.example/v1",
    "protocol": "chat",
}

DEFAULT_PROVIDER_MAPPED = {
    "plugin.model.name": "default-model",
    "plugin.model.api_key": "default-key",
    "plugin.model.base_url": "https://default.example/v1",
    "plugin.model.protocol": "chat",
}


def test_default_llm_waits_for_llm_bundle_then_creates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scope = FakeScope(modules=REQUIRED_MODULES - {LLM_MODULE})
    plugin = make_directory(configs=FakeConfigs(DEFAULT_PROVIDER), scope=scope)
    assert "llm@default" not in plugin._scope.instances

    scope.modules.add(LLM_MODULE)
    plugin._materialize_all()

    assert "llm@default" in plugin._scope.instances
    assert "Could not create the default LLM" not in caplog.text


def test_empty_llm_binding_inherits_providers_default() -> None:
    plugin = make_directory(configs=FakeConfigs(DEFAULT_PROVIDER))
    plugin.apply_agent_config(
        "simple_agent", {"llm": {"enabled": True, "properties": {}}}
    )

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties == {**DEFAULT_PROVIDER_MAPPED, "plugin.agent_id": "simple_agent"}


def test_empty_llm_binding_without_default_is_skipped() -> None:
    plugin = make_directory(configs=FakeConfigs(None))
    plugin.apply_agent_config(
        "simple_agent", {"llm": {"enabled": True, "properties": {}}}
    )

    assert "llm@simple_agent" not in plugin._scope.instances
    assert "agent-loop@simple_agent" in plugin._scope.instances


def test_partial_llm_binding_fills_missing_fields_from_default() -> None:
    plugin = make_directory(configs=FakeConfigs(DEFAULT_PROVIDER))
    plugin.apply_agent_config(
        "simple_agent",
        {"llm": {"enabled": True, "properties": {"plugin.model.name": "stored"}}},
    )

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties["plugin.model.name"] == "stored"
    assert descriptor.properties["plugin.model.api_key"] == "default-key"
    assert (
        descriptor.properties["plugin.model.base_url"]
        == "https://default.example/v1"
    )
    assert descriptor.properties["plugin.model.protocol"] == "chat"


def test_llm_binding_materialization_waits_for_llm_bundle() -> None:
    scope = FakeScope(modules=REQUIRED_MODULES - {LLM_MODULE})
    plugin = make_directory(configs=FakeConfigs(DEFAULT_PROVIDER), scope=scope)
    plugin.apply_agent_config(
        "simple_agent", {"llm": {"enabled": True, "properties": {}}}
    )

    assert plugin._scope.instances == {}
    assert "simple_agent" not in plugin._failed

    scope.modules.add(LLM_MODULE)
    plugin._materialize_all()

    assert "llm@simple_agent" in plugin._scope.instances
    assert "llm@default" in plugin._scope.instances


def test_ensure_plugin_instance_fills_missing_fields_from_default() -> None:
    plugin = make_directory(configs=FakeConfigs(DEFAULT_PROVIDER))

    plugin.ensure_plugin_instance(
        "simple_agent", "llm", {"plugin.model.name": "request-model"}
    )

    descriptor = plugin._scope.instances["llm@simple_agent"]
    assert descriptor.properties["plugin.model.name"] == "request-model"
    assert descriptor.properties["plugin.model.api_key"] == "default-key"
    assert (
        descriptor.properties["plugin.model.base_url"]
        == "https://default.example/v1"
    )


def test_ensure_plugin_instance_skips_unconfigured() -> None:
    plugin = make_directory(configs=FakeConfigs(None))

    plugin.ensure_plugin_instance("simple_agent", "llm", {})

    assert "llm@simple_agent" not in plugin._scope.instances
