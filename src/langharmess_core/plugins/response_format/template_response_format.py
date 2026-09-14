"""Response format plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess_core.contracts import ResponseFormatProvider


@ComponentFactory("response-format-plugin-factory")
@Provides(ResponseFormatProvider)
@Property("_plugin_name", "plugin.name", "response-format-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_response_format", "plugin.response_format", None)
class TemplateResponseFormatPlugin:
    def __init__(self) -> None:
        self._plugin_name = "response-format-plugin"
        self._plugin_version = "1.0.0"
        self._response_format: Any = None

    def get_response_format(self) -> Any:
        return self._response_format
