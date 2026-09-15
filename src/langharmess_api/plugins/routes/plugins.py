"""Plugin configuration route: current config, history, and rollback."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel

from langharmess_api.contracts import RouteProvider
from langharmess_core.contracts import AgentDirectoryProvider
from langharmess_plugin.config_store import PluginConfigStore, scope_path
from langharmess_plugin.contracts import ScopedPluginRegistrar
from langharmess_plugin.validation import ContractGuard

KNOWN_SCOPES = ("api", "cli")


class PluginsRequest(BaseModel):
    plugins: dict[str, Any] | None = None
    actor: str = "api"


class RollbackRequest(BaseModel):
    seq: int
    actor: str = "api"


@ComponentFactory("api-plugins-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "plugins")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_config_dir", "plugin.config_dir", "~/.langharmess")
@RequiresBest("_scope", ScopedPluginRegistrar, optional=True, immediate_rebind=True)
@RequiresBest(
    "_directory", AgentDirectoryProvider, optional=True, immediate_rebind=True
)
class PluginsRoutePlugin:
    """Serves the versioned plugin config and applies changes at runtime."""

    def __init__(self) -> None:
        self._plugin_name = "plugins"
        self._plugin_version = "1.0.0"
        self._config_dir = "~/.langharmess"
        self._scope: Any = None
        self._directory: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_scope": ContractGuard(self, "_scope", ScopedPluginRegistrar),
            "_directory": ContractGuard(self, "_directory", AgentDirectoryProvider),
        }

    @BindField("_scope", if_valid=True)
    def _on_scope_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_scope", if_valid=True)
    def _on_scope_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    @BindField("_directory", if_valid=True)
    def _on_directory_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_directory", if_valid=True)
    def _on_directory_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/plugins")
        def read_plugins(scope: str = Query(...)) -> dict[str, Any]:
            store = self._store(scope)
            return {
                "scope": scope,
                "version": store.current_seq(),
                "plugins": store.plugins(),
            }

        @router.put("/plugins")
        def update_plugins(
            payload: PluginsRequest = Body(...), scope: str = Query(...)
        ) -> dict[str, Any]:
            if payload.plugins is None:
                raise HTTPException(status_code=400, detail="plugins payload is required")
            store = self._store(scope)
            result = self._apply(scope, payload.plugins)
            version = store.update(payload.plugins, actor=payload.actor)
            return {"scope": scope, "version": version, **result}

        @router.get("/plugins/history")
        def read_history(scope: str = Query(...)) -> dict[str, Any]:
            store = self._store(scope)
            history = [
                {
                    "seq": entry.get("seq"),
                    "ts": entry.get("ts"),
                    "action": entry.get("action"),
                    "actor": entry.get("actor"),
                    "target_seq": entry.get("target_seq"),
                }
                for entry in store.history()
            ]
            return {"scope": scope, "version": store.current_seq(), "history": history}

        @router.post("/plugins/rollback")
        def rollback(
            payload: RollbackRequest = Body(...), scope: str = Query(...)
        ) -> dict[str, Any]:
            store = self._store(scope)
            try:
                target = store.config_of(payload.seq)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            result = self._apply(scope, target.get("plugins", {}))
            version = store.rollback(payload.seq, actor=payload.actor)
            return {"scope": scope, "version": version, **result}

        return router

    def _store(self, scope: str) -> PluginConfigStore:
        self._validate_scope(scope)
        return PluginConfigStore.load(scope_path(self._config_dir, scope), scope)

    def _validate_scope(self, scope: str) -> None:
        if scope in KNOWN_SCOPES:
            return
        if scope.startswith("agent:") and len(scope) > len("agent:"):
            return
        raise HTTPException(status_code=400, detail=f"Unknown scope: {scope}")

    def _apply(self, scope: str, plugins: dict[str, Any]) -> dict[str, list[str]]:
        if scope == "api":
            if self._scope is None:
                raise HTTPException(
                    status_code=503, detail="Plugin scope service unavailable"
                )
            try:
                result: dict[str, list[str]] = self._scope.apply_config(plugins)
                return result
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if scope.startswith("agent:"):
            if self._directory is None:
                raise HTTPException(
                    status_code=503, detail="Agent directory unavailable"
                )
            agent_id = scope.split(":", 1)[1]
            try:
                self._directory.apply_agent_config(agent_id, plugins)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"applied": sorted(plugins), "restart_required": []}
        # The CLI process owns its plugin set, so it picks changes up on restart.
        return {"applied": [], "restart_required": sorted(plugins)}

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
