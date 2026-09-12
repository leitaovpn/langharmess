"""Store plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess.contracts import SPEC_STORE


@ComponentFactory("store-plugin-factory")
@Provides(SPEC_STORE)
@Property("_plugin_name", "plugin.name", "store-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_store", "plugin.store", None)
class TemplateStorePlugin:
    def __init__(self) -> None:
        self._plugin_name = "store-plugin"
        self._plugin_version = "1.0.0"
        self._store: Any = None

    def get_store(self) -> Any:
        return self._store
