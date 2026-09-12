"""Health route plugin template."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import SPEC_ROUTE
from langharmess_api.dependencies import get_db_session


@ComponentFactory("api-health-route-template-factory")
@Provides(SPEC_ROUTE)
@Property("_plugin_name", "plugin.name", "template-health")
@Property("_plugin_version", "plugin.version", "1.0.0")
class TemplateHealthRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "template-health"
        self._plugin_version = "1.0.0"

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/health")
        def health(db: dict[str, bool] = Depends(get_db_session)) -> dict[str, object]:
            return {"status": "ok", "db": db.get("connected")}

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
