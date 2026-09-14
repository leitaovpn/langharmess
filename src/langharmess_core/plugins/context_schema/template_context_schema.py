"""Context schema plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess_core.contracts import ContextSchemaProvider


@ComponentFactory("context-schema-plugin-factory")
@Provides(ContextSchemaProvider)
@Property("_plugin_name", "plugin.name", "context-schema-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_context_schema", "plugin.context_schema", None)
class TemplateContextSchemaPlugin:
    def __init__(self) -> None:
        self._plugin_name = "context-schema-plugin"
        self._plugin_version = "1.0.0"
        self._context_schema: Any = None

    def get_context_schema(self) -> Any:
        return self._context_schema
