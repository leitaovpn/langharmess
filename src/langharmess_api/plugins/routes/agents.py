"""Agent registry route plugin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)

from langharmess_api.contracts import RouteProvider
from langharmess_core.contracts import (
    AgentDirectoryProvider,
    AgentRegistryProvider,
)
from langharmess_plugin.validation import ContractGuard


@ComponentFactory("api-agents-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "agents")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_agent_registry", AgentRegistryProvider, optional=True, immediate_rebind=True
)
@RequiresBest(
    "_agent_directory", AgentDirectoryProvider, optional=True, immediate_rebind=True
)
class AgentsRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "agents"
        self._plugin_version = "1.0.0"
        self._agent_registry: Any = None
        self._agent_directory: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_agent_registry": ContractGuard(
                self, "_agent_registry", AgentRegistryProvider
            ),
            "_agent_directory": ContractGuard(
                self, "_agent_directory", AgentDirectoryProvider
            ),
        }

    @BindField("_agent_registry", if_valid=True)
    def _on_agent_registry_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_agent_registry")
    def _on_agent_registry_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    @BindField("_agent_directory", if_valid=True)
    def _on_agent_directory_bind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].admit(service)

    @UnbindField("_agent_directory")
    def _on_agent_directory_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/agents")
        def list_agents() -> dict[str, Any]:
            if self._agent_directory is not None:
                return {"agents": self._agent_directory.list_agents()}
            if self._agent_registry is None:
                raise HTTPException(
                    status_code=503, detail="Agent registry unavailable"
                )
            return {"agents": self._agent_registry.list_agents()}

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
