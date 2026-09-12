"""Cache plugin."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess.contracts import SPEC_CACHE


@ComponentFactory("cache-plugin-factory")
@Provides(SPEC_CACHE)
@Property("_plugin_name", "plugin.name", "cache-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_cache", "plugin.cache", None)
class CachePlugin:
    def __init__(self) -> None:
        self._plugin_name = "cache-plugin"
        self._plugin_version = "1.0.0"
        self._cache: Any = None

    def get_cache(self) -> Any:
        return self._cache
