"""Unit tests for the scoped plugin registrar service."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from typing import Any, Protocol
from unittest.mock import Mock

import pytest

import langharmess_plugin.plugin_manager as pm_module
from langharmess_plugin.contracts import (
    SPEC_PLUGIN_SCOPE,
    PluginRegistrar,
    ScopedPluginRegistrar,
)
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.validation import contract_for, service_contract


@service_contract("test.scope.service")
class ScopeLike(Protocol):
    def get_tools(self) -> list[Any]: ...


class _Conforming:
    def get_tools(self) -> list[Any]:
        return []


def descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="scoped",
        version="1.0.0",
        module="module.scoped",
        factory="scoped-factory",
        instance="scoped",
        specification="test.scope.service",
    )


def make_manager(*, started: bool = True) -> PluginManager:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    manager._context.install_bundle.return_value = Mock()
    if started:
        manager._ipopo.instantiate.return_value = _Conforming()
        manager.install_plugin(descriptor())
        manager._ipopo.instantiate.reset_mock()
        manager._ipopo.instantiate.return_value = _Conforming()
    return manager


def scoped_descriptor(**properties: Any) -> PluginDescriptor:
    item = descriptor()
    item.instance = "scoped@ag1"
    item.properties = properties
    return item


def test_scoped_registrar_contract_is_pinned() -> None:
    assert SPEC_PLUGIN_SCOPE == "plugin.scope"
    assert contract_for(SPEC_PLUGIN_SCOPE) is ScopedPluginRegistrar


def test_manager_registers_itself_under_both_specifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = Mock()
    framework = Mock()
    framework.get_bundle_context.return_value = context
    context.get_service_reference.return_value = Mock()
    context.get_service.return_value = Mock()
    monkeypatch.setattr(pm_module, "create_framework", lambda services: framework)

    manager = PluginManager(PluginRegistry())
    manager.start()

    registered = [call.args[0] for call in context.register_service.call_args_list]
    assert PluginRegistrar in registered
    assert ScopedPluginRegistrar in registered


def test_find_service_returns_none_without_match() -> None:
    manager = make_manager()
    manager._context.get_service_reference.return_value = None
    assert manager.find_service("agent.plugin.llm") is None


def test_find_service_passes_the_filter_to_pelix() -> None:
    manager = make_manager()
    reference = Mock()
    manager._context.get_service_reference.return_value = reference

    manager.find_service("agent.plugin.llm", filter="(plugin.agent_id=ag1)")

    manager._context.get_service_reference.assert_called_once_with(
        "agent.plugin.llm", "(plugin.agent_id=ag1)"
    )
    manager._context.get_service.assert_called_once_with(reference)


def test_find_service_requires_started_manager() -> None:
    manager = PluginManager(PluginRegistry())
    with pytest.raises(RuntimeError, match="not started"):
        manager.find_service("agent.plugin.llm")


@pytest.mark.parametrize(
    "bad_filter",
    ["(plugin.agent_id=ag1", "no parens at all", "(unbalanced))", ""],
)
def test_instantiate_instance_rejects_malformed_filters(bad_filter: str) -> None:
    manager = make_manager()
    item = scoped_descriptor(
        **{"requires.filters": {"_llm_provider": bad_filter}}
    )

    with pytest.raises(ValueError, match="filter"):
        manager.instantiate_instance(item)

    manager._ipopo.instantiate.assert_not_called()


def test_instantiate_instance_rejects_invalid_filter_shapes() -> None:
    manager = make_manager()
    item = scoped_descriptor(**{"requires.filters": "not-a-dict"})

    with pytest.raises(ValueError, match="filters"):
        manager.instantiate_instance(item)


def test_instantiate_instance_rejects_non_text_filter_values() -> None:
    manager = make_manager()
    item = scoped_descriptor(**{"requires.filters": {"_llm_provider": 42}})

    with pytest.raises(ValueError, match="filter"):
        manager.instantiate_instance(item)


def test_instantiate_instance_accepts_valid_filters() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = _Conforming()
    item = scoped_descriptor(
        **{
            "plugin.agent_id": "ag1",
            "requires.filters": {"_llm_provider": "(plugin.agent_id=ag1)"},
        }
    )

    manager.instantiate_instance(item)

    manager._ipopo.instantiate.assert_called_once()


def test_apply_config_marks_hot_plugins_as_applied() -> None:
    manager = make_manager()
    manager.registry.get("scoped").swap_policy = "hot"

    result = manager.apply_config(
        {"scoped": {"enabled": True, "properties": {"plugin.mode": "fast"}}}
    )

    assert result == {"applied": ["scoped"], "restart_required": []}
    assert manager.registry.get("scoped").properties["plugin.mode"] == "fast"


def test_apply_config_requires_restart_for_restart_plugins() -> None:
    manager = make_manager()
    before = manager.registry.get("scoped")

    result = manager.apply_config(
        {"scoped": {"enabled": True, "properties": {"plugin.mode": "slow"}}}
    )

    assert result == {"applied": [], "restart_required": ["scoped"]}
    assert manager.registry.get("scoped").properties == before.properties


def test_apply_config_reports_unchanged_plugins_as_applied() -> None:
    manager = make_manager()
    result = manager.apply_config({"scoped": {"enabled": True}})
    assert result == {"applied": [], "restart_required": []}


def test_apply_config_reverts_removed_overrides() -> None:
    manager = make_manager()
    manager.registry.get("scoped").swap_policy = "hot"
    manager.apply_config({"scoped": {"properties": {"plugin.mode": "fast"}}})
    assert manager.registry.get("scoped").properties["plugin.mode"] == "fast"

    result = manager.apply_config({})

    assert result == {"applied": ["scoped"], "restart_required": []}
    assert "plugin.mode" not in manager.registry.get("scoped").properties


def test_apply_config_rejects_unknown_plugins() -> None:
    manager = make_manager()
    with pytest.raises(ValueError, match="Unknown plugin: ghost"):
        manager.apply_config({"ghost": {"enabled": True}})


def test_apply_config_disables_hot_plugins() -> None:
    manager = make_manager()
    manager.registry.get("scoped").swap_policy = "hot"

    result = manager.apply_config({"scoped": {"enabled": False}})

    assert result == {"applied": ["scoped"], "restart_required": []}
    assert manager.registry.get("scoped").enabled is False
