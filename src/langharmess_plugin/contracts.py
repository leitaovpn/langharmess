"""Public contracts for runtime plugin management services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.validation import service_contract
from langharmess_scope import ScopeId

SPEC_PLUGIN_REGISTRAR = "plugin.registrar"
SPEC_PLUGIN_SCOPE = "plugin.scope"


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
