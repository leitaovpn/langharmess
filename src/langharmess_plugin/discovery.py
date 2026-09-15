"""Discovery of side-effect-free plugin declarations through entry points."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, cast

from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
from langharmess_plugin.package import PluginPackage

ENTRY_POINT_GROUP = "langharmess.plugins"
VALID_TARGETS = {"root", "ui", "server", "agent", "agent_instance"}


class PluginDiscoveryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryFailure:
    entry_point: str
    value: str
    detail: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    packages: tuple[PluginPackage, ...]
    failures: tuple[DiscoveryFailure, ...]


def _installed_entry_points() -> Iterable[EntryPoint]:
    return entry_points(group=ENTRY_POINT_GROUP)


class PluginDiscovery:
    def __init__(
        self,
        loader: Callable[[], Iterable[Any]] = _installed_entry_points,
    ) -> None:
        self._loader = loader

    def scan(self) -> DiscoveryResult:
        packages: list[PluginPackage] = []
        failures: list[DiscoveryFailure] = []
        for entry_point in self._loader():
            try:
                factory = entry_point.load()
                if not callable(factory):
                    raise PluginDiscoveryError(
                        f"Entry point {entry_point.name!r} must be callable"
                    )
                package = factory()
                self._validate_package(package)
                packages.append(cast(PluginPackage, package))
            except Exception as exc:
                failures.append(
                    DiscoveryFailure(
                        str(entry_point.name), str(entry_point.value), str(exc)
                    )
                )
        self._validate_catalog(packages)
        return DiscoveryResult(tuple(packages), tuple(failures))

    def discover(self) -> tuple[PluginPackage, ...]:
        result = self.scan()
        if result.failures:
            raise PluginDiscoveryError(result.failures[0].detail)
        return result.packages

    @staticmethod
    def _validate_package(package: Any) -> None:
        if not isinstance(package, PluginPackage):
            raise PluginDiscoveryError("Entry point did not return PluginPackage")
        if not package.id.strip() or not package.version.strip():
            raise PluginDiscoveryError("Plugin package id and version must be non-empty")
        contribution_ids: set[str] = set()
        for contribution in package.contributions:
            if contribution.id in contribution_ids:
                raise PluginDiscoveryError(
                    f"Duplicate contribution {contribution.id!r} in {package.id!r}"
                )
            contribution_ids.add(contribution.id)
            if contribution.target not in VALID_TARGETS:
                raise PluginDiscoveryError(
                    f"Invalid contribution target: {contribution.target!r}"
                )
            if (
                contribution.tool_exports
                and contribution.descriptor.specification != SPEC_TOOL_EXPORT_TARGET
            ):
                raise PluginDiscoveryError(
                    "Tool exports require the plugin.tool_export.target specification"
                )

    @staticmethod
    def _validate_catalog(packages: list[PluginPackage]) -> None:
        package_ids: set[str] = set()
        descriptor_names: set[str] = set()
        descriptor_instances: set[str] = set()
        for package in packages:
            if package.id in package_ids:
                raise PluginDiscoveryError(f"Duplicate plugin package: {package.id!r}")
            package_ids.add(package.id)
            for contribution in package.contributions:
                descriptor = contribution.descriptor
                if descriptor.name in descriptor_names:
                    raise PluginDiscoveryError(
                        f"Duplicate plugin descriptor: {descriptor.name!r}"
                    )
                if descriptor.instance in descriptor_instances:
                    raise PluginDiscoveryError(
                        f"Duplicate plugin instance: {descriptor.instance!r}"
                    )
                descriptor_names.add(descriptor.name)
                descriptor_instances.add(descriptor.instance)
