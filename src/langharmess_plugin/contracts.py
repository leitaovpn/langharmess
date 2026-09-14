"""Public contracts for runtime plugin management services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.validation import service_contract

SPEC_PLUGIN_REGISTRAR = "plugin.registrar"


@service_contract(SPEC_PLUGIN_REGISTRAR)
@runtime_checkable
class PluginRegistrar(Protocol):
    def ensure_plugin(self, descriptor: PluginDescriptor) -> None: ...
