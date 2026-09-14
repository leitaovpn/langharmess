"""Health route plugin."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import RouteProvider
from langharmess_core.common.dependencies import get_db_session


@ComponentFactory("api-health-plugin-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "health")
@Property("_plugin_version", "plugin.version", "1.0.0")
class HealthRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "health"
        self._plugin_version = "1.0.0"

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/health")
        def health(db: dict[str, bool] = Depends(get_db_session)) -> dict[str, object]:
            return {"status": "ok", "db": db.get("connected")}

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
