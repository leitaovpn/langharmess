"""Contract enforcement tests: install-time rejection and bind-time quarantine."""

from __future__ import annotations

from typing import Any, Protocol
from unittest.mock import Mock

import pytest

from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.validation import ContractViolationError, service_contract


@service_contract("test.enforce.tool")
class ToolLike(Protocol):
    def get_tools(self) -> list[Any]: ...


class Conforming:
    def get_tools(self) -> list[Any]:
        return []


class NonConforming:
    def get_tools(self, root: str) -> list[Any]:
        return []


def _descriptor(specification: str) -> PluginDescriptor:
    return PluginDescriptor(
        name="probe",
        version="1.0.0",
        module="module.probe",
        factory="probe-factory",
        instance="probe",
        specification=specification,
    )


def _manager_with_instance(instance: Any) -> PluginManager:
    manager = PluginManager(PluginRegistry())
    manager._framework = Mock()
    manager._context = Mock()
    manager._ipopo = Mock()
    manager._ipopo.instantiate.return_value = instance
    manager._context.install_bundle.return_value = Mock()
    return manager


def test_install_rejects_non_conforming_component() -> None:
    manager = _manager_with_instance(NonConforming())

    with pytest.raises(ContractViolationError) as excinfo:
        manager.install_plugin(_descriptor("test.enforce.tool"))

    assert excinfo.value.plugin == "probe"
    assert "PARAM_EXTRA_REQUIRED" in str(excinfo.value)
    manager._ipopo.kill.assert_called_once_with("probe")
    assert "probe" not in manager._bound
    assert manager._ipopo.instantiate.call_count == 1


def test_install_accepts_conforming_component() -> None:
    manager = _manager_with_instance(Conforming())

    manager.install_plugin(_descriptor("test.enforce.tool"))

    assert manager.installed_names() == {"probe"}
    assert "probe" in manager._bound
    manager._ipopo.kill.assert_not_called()


def test_install_skips_unpinned_specification() -> None:
    manager = _manager_with_instance(NonConforming())

    manager.install_plugin(_descriptor("test.enforce.unpinned"))

    assert "probe" in manager._bound
    manager._ipopo.kill.assert_not_called()
