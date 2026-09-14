"""Echo route plugin."""

from __future__ import annotations

from fastapi import APIRouter
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import SPEC_ROUTE


@ComponentFactory("api-echo-plugin-factory")
@Provides(SPEC_ROUTE)
@Property("_plugin_name", "plugin.name", "echo")
@Property("_plugin_version", "plugin.version", "1.0.0")
class EchoRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "echo"
        self._plugin_version = "1.0.0"

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/echo")
        def echo() -> dict[str, str]:
            return {"echo": "ok"}

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
