"""In-memory database plugin template."""

from __future__ import annotations

from collections.abc import Callable

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import SPEC_DB


@ComponentFactory("api-db-template-factory")
@Provides(SPEC_DB)
@Property("_plugin_name", "plugin.name", "template-db")
@Property("_plugin_version", "plugin.version", "1.0.0")
class TemplateDBPlugin:
    def __init__(self) -> None:
        self._plugin_name = "template-db"
        self._plugin_version = "1.0.0"

    def get_session_dependency(self) -> Callable[[], dict[str, bool]]:
        def dependency() -> dict[str, bool]:
            return {"connected": True}

        return dependency

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
