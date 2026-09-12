"""Checkpointer plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess_core.contracts import SPEC_CHECKPOINTER


@ComponentFactory("checkpointer-plugin-factory")
@Provides(SPEC_CHECKPOINTER)
@Property("_plugin_name", "plugin.name", "checkpointer-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_checkpointer", "plugin.checkpointer", None)
class TemplateCheckpointerPlugin:
    def __init__(self) -> None:
        self._plugin_name = "checkpointer-plugin"
        self._plugin_version = "1.0.0"
        self._checkpointer: Any = None

    def get_checkpointer(self) -> Any:
        return self._checkpointer
