"""Interrupt-after plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess.contracts import SPEC_INTERRUPT_AFTER


@ComponentFactory("interrupt-after-plugin-factory")
@Provides(SPEC_INTERRUPT_AFTER)
@Property("_plugin_name", "plugin.name", "interrupt-after-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.interrupt_after", None)
class InterruptAfterPlugin:
    def __init__(self) -> None:
        self._plugin_name = "interrupt-after-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_interrupt_after(self) -> list[str]:
        return list(self._items or [])
