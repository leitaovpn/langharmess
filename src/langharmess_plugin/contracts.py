"""Public contracts for runtime plugin management services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.validation import service_contract

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

    def instantiate_instance(self, descriptor: PluginDescriptor) -> None: ...

    def kill_instance(self, instance: str) -> None: ...

    def find_service(
        self, specification: str, filter: str | None = None
    ) -> Any | None: ...

    def installed_modules(self) -> set[str]: ...
