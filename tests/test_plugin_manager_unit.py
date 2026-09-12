"""Unit tests for PluginManager error and mock-backed branches."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from unittest.mock import Mock

import pytest

from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry


def descriptor(name: str, enabled: bool = True) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module=f"module.{name}",
        factory=f"{name}-factory",
        instance=name,
        specification=f"agent.plugin.{name}",
        enabled=enabled,
    )


def make_started_manager() -> PluginManager:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    return manager


def test_manager_not_started_errors_and_stop_is_noop() -> None:
    manager = PluginManager(PluginRegistry())
    assert manager.started is False
    manager.stop()

    with pytest.raises(RuntimeError, match="not started"):
        manager.install_plugin(descriptor("llm"))
    with pytest.raises(RuntimeError, match="not started"):
        manager.get_service("agent.plugin.llm")
    with pytest.raises(RuntimeError, match="not started"):
        manager.get_services("agent.plugin.llm")
    with pytest.raises(RuntimeError, match="not started"):
        manager.service_properties("agent.plugin.llm")


def test_manager_start_twice_raises() -> None:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    with pytest.raises(RuntimeError, match="already started"):
        manager.start()


def test_install_unbound_and_uninstall_paths() -> None:
    manager = make_started_manager()
    manager._context.install_bundle.return_value = Mock()
    item = descriptor("disabled", enabled=False)

    manager.install_plugin(item)
    assert manager.installed_names() == {"disabled"}
    manager._ipopo.instantiate.assert_not_called()

    manager.uninstall_plugin("disabled")
    assert manager.installed_names() == set()
    manager._context.install_bundle.return_value.stop.assert_called_once()
    manager._context.install_bundle.return_value.uninstall.assert_called_once()


def test_install_bound_duplicate_and_rebind_paths() -> None:
    manager = make_started_manager()
    manager._context.install_bundle.return_value = Mock()
    item = descriptor("llm")

    manager.install_plugin(item)
    manager._ipopo.instantiate.assert_called_once_with("llm-factory", "llm", None)

    with pytest.raises(ValueError, match="already installed"):
        manager.install_plugin(item)
    with pytest.raises(ValueError, match="already bound"):
        manager.bind_plugin("llm")

    manager.unbind_plugin("llm")
    manager._ipopo.kill.assert_called_once_with("llm")

    manager.bind_plugin("llm")
    assert manager._ipopo.instantiate.call_count == 2


def test_missing_plugin_lifecycle_errors() -> None:
    manager = make_started_manager()
    with pytest.raises(KeyError):
        manager.uninstall_plugin("missing")
    with pytest.raises(KeyError):
        manager.bind_plugin("missing")
    with pytest.raises(KeyError):
        manager.unbind_plugin("missing")
    with pytest.raises(KeyError):
        manager._get_descriptor("missing")


def test_unbind_not_bound_raises() -> None:
    manager = make_started_manager()
    manager._context.install_bundle.return_value = Mock()
    item = descriptor("disabled", enabled=False)
    manager.install_plugin(item)

    with pytest.raises(ValueError, match="not bound"):
        manager.unbind_plugin("disabled")


def test_service_queries_with_mock_context() -> None:
    manager = make_started_manager()
    manager._context.get_service_reference.return_value = None
    assert manager.get_service("missing") is None

    manager._context.get_all_service_references.return_value = None
    assert manager.get_services("missing") == []
    assert manager.service_properties("missing") == []


def test_replace_plugin_replaces_descriptor_and_component() -> None:
    manager = make_started_manager()
    manager._context.install_bundle.return_value = Mock()
    old = descriptor("llm")
    manager.install_plugin(old)
    replacement = descriptor("llm")
    replacement.properties = {"plugin.model.name": "new-model"}

    manager.replace_plugin(replacement)

    assert manager.registry.get("llm") is replacement
    assert manager.installed_names() == {"llm"}
    assert manager._ipopo.instantiate.call_args_list[-1].args == (
        "llm-factory",
        "llm",
        {"plugin.model.name": "new-model"},
    )

    calls = manager._ipopo.instantiate.call_count
    manager.ensure_plugin(replacement)
    assert manager._ipopo.instantiate.call_count == calls
