"""In-memory database plugin."""

from __future__ import annotations

from collections.abc import Callable

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_api.contracts import DBProvider


@ComponentFactory("api-db-plugin-factory")
@Provides(DBProvider)
@Property("_plugin_name", "plugin.name", "db")
@Property("_plugin_version", "plugin.version", "1.0.0")
class DBPlugin:
    def __init__(self) -> None:
        self._plugin_name = "db"
        self._plugin_version = "1.0.0"

    def get_session_dependency(self) -> Callable[[], dict[str, bool]]:
        def dependency() -> dict[str, bool]:
            return {"connected": True}

        return dependency

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
