"""Scope tree route: the runtime scope hierarchy."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)

from langharness_api.common.errors import http_error
from langharness_api.contracts import RouteProvider
from langharness_plugin.contracts import DynamicPluginManager
from langharness_plugin.validation import ContractGuard


@ComponentFactory("api-scopes-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "scopes")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_dynamic", DynamicPluginManager, optional=True, immediate_rebind=True)
class ScopesRoutePlugin:
    """Serves the runtime scope tree."""

    def __init__(self) -> None:
        self._plugin_name = "scopes"
        self._plugin_version = "1.0.0"
        self._dynamic: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_dynamic": ContractGuard(self, "_dynamic", DynamicPluginManager),
        }

    @BindField("_dynamic", if_valid=True)
    def _on_dynamic_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_dynamic", if_valid=True)
    def _on_dynamic_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/scope")
        def read_scope() -> dict[str, Any]:
            dynamic = self._require_dynamic()
            return {
                "scopes": [
                    {
                        "id": str(scope.id),
                        "parent_id": (
                            str(scope.parent_id)
                            if scope.parent_id is not None
                            else None
                        ),
                        "name": scope.name,
                    }
                    for scope in dynamic.scopes()
                ]
            }

        return router

    def _require_dynamic(self) -> Any:
        if self._dynamic is None:
            raise http_error(
                503,
                "Dynamic plugin manager unavailable",
                code="SERVICE_UNAVAILABLE",
                error_type="ServiceUnavailable",
            )
        return self._dynamic

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
