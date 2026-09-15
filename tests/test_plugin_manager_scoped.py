"""Unit tests for scoped plugin instances (per-agent plugin sets)."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from typing import Any, Protocol
from unittest.mock import Mock

import pytest

from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.validation import (
    ContractViolationError,
    service_contract,
)

INSTALLED_MODULE = "module.scoped"


@service_contract("test.scoped.tool")
class ToolLike(Protocol):
    def get_tools(self) -> list[Any]: ...


class Conforming:
    def get_tools(self) -> list[Any]:
        return []


class NonConforming:
    def get_tools(self, root: str) -> list[Any]:
        return []


def base_descriptor() -> PluginDescriptor:
    return PluginDescriptor(
        name="scoped-bundle",
        version="1.0.0",
        module=INSTALLED_MODULE,
        factory="scoped-factory",
        instance="scoped",
        specification="test.scoped.tool",
    )


def scoped_descriptor(agent_id: str = "ag1") -> PluginDescriptor:
    return PluginDescriptor(
        name=f"scoped@{agent_id}",
        version="1.0.0",
        module=INSTALLED_MODULE,
        factory="scoped-factory",
        instance=f"scoped@{agent_id}",
        specification="test.scoped.tool",
        properties={"plugin.agent_id": agent_id},
    )


def make_manager(*, installed: bool = True) -> PluginManager:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    manager._context.install_bundle.return_value = Mock()
    if installed:
        manager._ipopo.instantiate.return_value = Conforming()
        manager.install_plugin(base_descriptor())
        manager._ipopo.instantiate.reset_mock()
        manager._ipopo.instantiate.return_value = Conforming()
    return manager


def test_instantiate_instance_requires_started_manager() -> None:
    manager = PluginManager(PluginRegistry())
    with pytest.raises(RuntimeError, match="not started"):
        manager.instantiate_instance(scoped_descriptor())


def test_instantiate_instance_requires_installed_module() -> None:
    manager = make_manager(installed=False)
    with pytest.raises(ValueError, match="not installed"):
        manager.instantiate_instance(scoped_descriptor())


def test_instantiate_instance_passes_properties_and_tracks_instance() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = Conforming()

    descriptor = scoped_descriptor("ag1")
    manager.instantiate_instance(descriptor)

    manager._ipopo.instantiate.assert_called_once_with(
        "scoped-factory", "scoped@ag1", {"plugin.agent_id": "ag1"}
    )
    assert manager.scoped_instances() == {"scoped@ag1": descriptor}


def test_instantiate_instance_rejects_duplicate_instance() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = Conforming()
    manager.instantiate_instance(scoped_descriptor("ag1"))
    with pytest.raises(ValueError, match="already instantiated"):
        manager.instantiate_instance(scoped_descriptor("ag1"))


def test_instantiate_instance_kills_contract_violators() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = NonConforming()
    with pytest.raises(ContractViolationError):
        manager.instantiate_instance(scoped_descriptor("ag1"))
    manager._ipopo.kill.assert_called_once_with("scoped@ag1")
    assert manager.scoped_instances() == {}


def test_kill_instance_removes_it() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = Conforming()
    manager.instantiate_instance(scoped_descriptor("ag1"))

    manager.kill_instance("scoped@ag1")

    manager._ipopo.kill.assert_called_once_with("scoped@ag1")
    assert manager.scoped_instances() == {}


def test_kill_instance_rejects_unknown_instance() -> None:
    manager = make_manager()
    with pytest.raises(KeyError):
        manager.kill_instance("missing@ag1")


def test_installed_modules_track_bundle_modules() -> None:
    manager = make_manager()
    assert manager.installed_modules() == {INSTALLED_MODULE}
    manager.uninstall_plugin("scoped-bundle")
    assert manager.installed_modules() == set()


def test_stop_clears_scoped_instances() -> None:
    manager = make_manager()
    manager._ipopo.instantiate.return_value = Conforming()
    manager.instantiate_instance(scoped_descriptor("ag1"))

    manager.stop()

    assert manager.scoped_instances() == {}
    assert manager.installed_modules() == set()
