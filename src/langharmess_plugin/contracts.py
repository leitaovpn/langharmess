"""Public contracts for runtime plugin management services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from langharmess_plugin.registry import PluginDescriptor

SPEC_PLUGIN_REGISTRAR = "plugin.registrar"


@runtime_checkable
class PluginRegistrar(Protocol):
    def ensure_plugin(self, descriptor: PluginDescriptor) -> None: ...
