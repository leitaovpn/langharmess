"""Public contracts for runtime plugin management services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langharness_plugin.registry import PluginDescriptor
from langharness_plugin.state_store import PersistedPluginRegistration
from langharness_plugin.validation import service_contract
from langharness_scope import Scope, ScopeId

SPEC_PLUGIN_REGISTRAR = "plugin.registrar"
SPEC_PLUGIN_SCOPE = "plugin.scope"
SPEC_DYNAMIC_PLUGIN_MANAGER = "plugin.dynamic.manager"
SPEC_TOOL_EXPORT_TARGET = "plugin.tool_export.target"


@service_contract(SPEC_PLUGIN_REGISTRAR)
@runtime_checkable
class PluginRegistrar(Protocol):
    def ensure_plugin(self, descriptor: PluginDescriptor) -> None: ...


@service_contract(SPEC_PLUGIN_SCOPE)
@runtime_checkable
class ScopedPluginRegistrar(Protocol):
    """Creates extra component instances from already installed bundles."""

    def instantiate_instance(
        self,
        descriptor: PluginDescriptor,
        *,
        scope_id: ScopeId | None = None,
        plugin_key: str | None = None,
    ) -> None: ...

    def kill_instance(self, instance: str) -> None: ...

    def find_service(
        self, specification: str, filter: str | None = None
    ) -> Any | None: ...

    def find_services(
        self, specification: str, filter: str | None = None
    ) -> list[Any]: ...

    def installed_modules(self) -> set[str]: ...

    def ensure_scope(
        self,
        scope_id: ScopeId,
        *,
        name: str,
        parent_id: ScopeId | None = None,
    ) -> None: ...

    def remove_scope(self, scope_id: ScopeId, *, recursive: bool = False) -> None: ...

    def scope_filter(self, scope_id: ScopeId) -> str: ...

    def apply_config(
        self, overrides: dict[str, dict[str, Any]]
    ) -> dict[str, list[str]]: ...


@service_contract(SPEC_DYNAMIC_PLUGIN_MANAGER)
@runtime_checkable
class DynamicPluginManager(Protocol):
    def rescan(self) -> Any: ...

    def discovered(self) -> tuple[Any, ...]: ...

    def registrations(self) -> tuple[PersistedPluginRegistration, ...]: ...

    def install(
        self,
        package_id: str,
        contribution_id: str,
        *,
        scope_id: ScopeId | None = None,
    ) -> PersistedPluginRegistration: ...

    def set_enabled(
        self, name: str, enabled: bool, *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...

    def update_properties(
        self, name: str, properties: dict[str, Any], *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...

    def uninstall(self, name: str, *, scope_id: ScopeId) -> None: ...

    def upgrade(
        self, name: str, *, scope_id: ScopeId
    ) -> PersistedPluginRegistration: ...

    def scopes(self) -> tuple[Scope, ...]: ...


@service_contract(SPEC_TOOL_EXPORT_TARGET)
@runtime_checkable
class ToolExportTarget(Protocol):
    def invoke_export(self, operation: str, arguments: dict[str, Any]) -> Any: ...
