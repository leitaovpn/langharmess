"""Dynamic plugin package discovery and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from langharmess_api.plugin import builtin_package as api_builtin_package
from langharmess_cli.plugin import builtin_package as cli_builtin_package
from langharmess_config.plugin import builtin_package as config_builtin_package
from langharmess_core.plugin import (
    builtin_package as core_builtin_package,
)
from langharmess_core.plugin import (
    dynamic_package as core_dynamic_package,
)
from langharmess_logging.plugin import builtin_package as logging_builtin_package
from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
from langharmess_plugin.discovery import PluginDiscovery, PluginDiscoveryError
from langharmess_plugin.package import PluginContribution, PluginPackage, ToolExport
from langharmess_plugin.registry import PluginDescriptor


class EchoArgs(BaseModel):
    text: str


def descriptor(
    name: str,
    *,
    module: str = "example.plugin",
    specification: str = SPEC_TOOL_EXPORT_TARGET,
) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module=module,
        factory=f"{name}-factory",
        instance=name,
        specification=specification,
        scope="server",
        scope_parent="root",
    )


def descriptor_with_instance(name: str, instance: str) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module="example.plugin",
        factory=f"{name}-factory",
        instance=instance,
        specification=SPEC_TOOL_EXPORT_TARGET,
        scope="server",
        scope_parent="root",
    )


def package(package_id: str = "example.package") -> PluginPackage:
    return PluginPackage(
        id=package_id,
        version="1.0.0",
        contributions=(
            PluginContribution(
                id="echo",
                target="server",
                descriptor=descriptor("echo"),
                tool_exports=(
                    ToolExport("echo", "Echo text", "echo", EchoArgs),
                ),
            ),
        ),
    )


@dataclass
class FakeEntryPoint:
    name: str
    value: str
    loaded: Any

    def load(self) -> Any:
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


def builtin_packages() -> tuple[PluginPackage, ...]:
    return (
        api_builtin_package(),
        cli_builtin_package(),
        config_builtin_package(),
        core_builtin_package(),
        logging_builtin_package(),
    )


def test_discovers_packages_and_records_broken_entry_points() -> None:
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint("ok", "pkg:plugin", lambda: package()),
            FakeEntryPoint("bad", "broken:plugin", RuntimeError("broken")),
        ]
    )
    result = discovery.scan()
    assert [item.id for item in result.packages] == ["example.package"]
    assert result.failures[0].entry_point == "bad"
    assert "broken" in result.failures[0].detail


def test_rejects_duplicate_package_and_contribution_ids() -> None:
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint("one", "one:plugin", lambda: package()),
            FakeEntryPoint("two", "two:plugin", lambda: package()),
        ]
    )
    with pytest.raises(PluginDiscoveryError, match="Duplicate plugin package"):
        discovery.discover()

    duplicate = PluginPackage(
        id="duplicate-contributions",
        version="1",
        contributions=(
            PluginContribution("same", "server", descriptor("one")),
            PluginContribution("same", "server", descriptor("two")),
        ),
    )
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("duplicate", "pkg:plugin", lambda: duplicate)]
    )
    with pytest.raises(PluginDiscoveryError, match="Duplicate contribution"):
        discovery.discover()


def test_rejects_invalid_package_factory_and_target_scope() -> None:
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("value", "pkg:value", package())]
    )
    with pytest.raises(PluginDiscoveryError, match="must be callable"):
        discovery.discover()

    invalid = PluginPackage(
        id="invalid",
        version="1",
        contributions=(
            PluginContribution("bad", "invalid", descriptor("bad")),  # type: ignore[arg-type]
        ),
    )
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("invalid", "pkg:plugin", lambda: invalid)]
    )
    with pytest.raises(PluginDiscoveryError, match="target"):
        discovery.discover()


def test_discover_returns_packages_when_there_are_no_failures() -> None:
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("ok", "pkg:plugin", lambda: package())]
    )
    assert [item.id for item in discovery.discover()] == ["example.package"]


def test_rejects_non_package_factory_and_empty_metadata() -> None:
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("bad", "pkg:plugin", lambda: object())]
    )
    with pytest.raises(PluginDiscoveryError, match="did not return PluginPackage"):
        discovery.discover()

    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("empty", "pkg:plugin", lambda: PluginPackage("", "1", ()))]
    )
    with pytest.raises(PluginDiscoveryError, match="id and version"):
        discovery.discover()


def test_rejects_duplicate_descriptor_name_and_instance_across_packages() -> None:
    same_name = PluginPackage(
        "name-two",
        "1",
        (PluginContribution("one", "server", descriptor("echo")),),
    )
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint("one", "pkg:plugin", lambda: package()),
            FakeEntryPoint("two", "pkg:plugin", lambda: same_name),
        ]
    )
    with pytest.raises(PluginDiscoveryError, match="Duplicate plugin descriptor"):
        discovery.discover()

    shared_instance = PluginPackage(
        "instance-two",
        "1",
        (
            PluginContribution(
                "one",
                "server",
                descriptor_with_instance("other", "echo"),
            ),
        ),
    )
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint("one", "pkg:plugin", lambda: package()),
            FakeEntryPoint("two", "pkg:plugin", lambda: shared_instance),
        ]
    )
    with pytest.raises(PluginDiscoveryError, match="Duplicate plugin instance"):
        discovery.discover()


def test_rejects_tool_exports_without_target_specification() -> None:
    invalid = PluginPackage(
        "tool-exports",
        "1",
        (
            PluginContribution(
                "bad",
                "server",
                descriptor("bad", specification="example.service"),
                tool_exports=(ToolExport("bad", "Bad", "bad", EchoArgs),),
            ),
        ),
    )
    discovery = PluginDiscovery(
        lambda: [FakeEntryPoint("bad", "pkg:plugin", lambda: invalid)]
    )
    with pytest.raises(PluginDiscoveryError, match="tool_export.target"):
        discovery.discover()


def test_discovers_builtin_packages_from_runtime_plugin_directories() -> None:
    packages = builtin_packages()
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint(package.id, f"{package.id}:package", lambda package=package: package)
            for package in packages
        ]
    )

    result = discovery.scan()

    assert result.failures == ()
    assert [item.id for item in result.packages] == [
        "builtin.api",
        "builtin.cli",
        "builtin.config",
        "builtin.core",
        "builtin.logging",
    ]
    modules = {
        contribution.descriptor.module
        for package in result.packages
        for contribution in package.contributions
    }
    assert any(module.startswith("langharmess_api.plugins.") for module in modules)
    assert any(module.startswith("langharmess_cli.plugins.") for module in modules)
    assert any(module.startswith("langharmess_config.plugins.") for module in modules)
    assert any(module.startswith("langharmess_core.plugins.") for module in modules)
    assert any(module.startswith("langharmess_logging.plugins.") for module in modules)


def test_builtin_packages_are_declarative_and_do_not_share_names() -> None:
    names: set[str] = set()
    instances: set[str] = set()
    for package in builtin_packages():
        assert package.id.startswith("builtin.")
        for contribution in package.contributions:
            descriptor = contribution.descriptor
            assert descriptor.name not in names
            assert descriptor.instance not in instances
            names.add(descriptor.name)
            instances.add(descriptor.instance)


def test_dynamic_package_scans_cleanly_alongside_builtin_packages() -> None:
    packages = builtin_packages() + (core_dynamic_package(),)
    discovery = PluginDiscovery(
        lambda: [
            FakeEntryPoint(package.id, f"{package.id}:package", lambda package=package: package)
            for package in packages
        ]
    )

    result = discovery.scan()

    assert result.failures == ()
    assert "dynamic.core" in [item.id for item in result.packages]
