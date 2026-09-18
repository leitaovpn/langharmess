"""Interrupt-after plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_core.contracts import InterruptAfterProvider


@ComponentFactory("interrupt-after-plugin-factory")
@Provides(InterruptAfterProvider)
@Property("_plugin_name", "plugin.name", "interrupt-after-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.interrupt_after", None)
class TemplateInterruptAfterPlugin:
    def __init__(self) -> None:
        self._plugin_name = "interrupt-after-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_interrupt_after(self) -> list[str]:
        return list(self._items or [])
