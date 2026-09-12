"""Debug plugin."""

from __future__ import annotations

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess.contracts import SPEC_DEBUG


@ComponentFactory("debug-plugin-factory")
@Provides(SPEC_DEBUG)
@Property("_plugin_name", "plugin.name", "debug-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_debug", "plugin.debug", False)
class TemplateDebugPlugin:
    def __init__(self) -> None:
        self._plugin_name = "debug-plugin"
        self._plugin_version = "1.0.0"
        self._debug = False

    def get_debug(self) -> bool:
        return self._debug
