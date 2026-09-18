"""Session index route plugin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)

from langharness_api.contracts import RouteProvider
from langharness_core.common.ids import validate_id
from langharness_core.contracts import SessionIndexProvider
from langharness_plugin.validation import ContractGuard


@ComponentFactory("api-sessions-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "sessions")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_session_index", SessionIndexProvider, optional=True, immediate_rebind=True
)
class SessionsRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "sessions"
        self._plugin_version = "1.0.0"
        self._session_index: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_session_index": ContractGuard(self, "_session_index", SessionIndexProvider)
        }

    @BindField("_session_index", if_valid=True)
    def _on_session_index_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_session_index")
    def _on_session_index_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/sessions")
        async def list_sessions(
            user_id: str, limit: int = Query(default=50, ge=1, le=500)
        ) -> dict[str, Any]:
            if self._session_index is None:
                raise HTTPException(status_code=503, detail="Session index unavailable")
            try:
                validate_id(user_id, field="user_id")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            sessions = await self._session_index.list_sessions(user_id, limit=limit)
            return {"user_id": user_id, "sessions": sessions}

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
