"""State schema plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess_core.contracts import SPEC_STATE_SCHEMA


@ComponentFactory("state-schema-plugin-factory")
@Provides(SPEC_STATE_SCHEMA)
@Property("_plugin_name", "plugin.name", "state-schema-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_state_schema", "plugin.state_schema", None)
class TemplateStateSchemaPlugin:
    def __init__(self) -> None:
        self._plugin_name = "state-schema-plugin"
        self._plugin_version = "1.0.0"
        self._state_schema: Any = None

    def get_state_schema(self) -> Any:
        return self._state_schema
