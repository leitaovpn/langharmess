"""Interrupt-before plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_core.contracts import InterruptBeforeProvider


@ComponentFactory("interrupt-before-plugin-factory")
@Provides(InterruptBeforeProvider)
@Property("_plugin_name", "plugin.name", "interrupt-before-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.interrupt_before", None)
class TemplateInterruptBeforePlugin:
    def __init__(self) -> None:
        self._plugin_name = "interrupt-before-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_interrupt_before(self) -> list[str]:
        return list(self._items or [])
