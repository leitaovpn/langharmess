"""Human-in-the-loop resume route plugin."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel

from langharness_api.contracts import RouteProvider
from langharness_core.common.ids import thread_key, validate_id
from langharness_core.contracts import AgentDirectoryProvider, SessionIndexProvider
from langharness_plugin.validation import ContractGuard


class ResumeRequest(BaseModel):
    decision: str | dict[str, Any]
    session_id: str
    user_id: str = "local_user"
    agent_id: str = "simple_agent"

@ComponentFactory("api-resume-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "resume")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_directory", AgentDirectoryProvider, optional=True, immediate_rebind=True)
@RequiresBest("_session_index", SessionIndexProvider, optional=True, immediate_rebind=True)
class ResumeRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name, self._plugin_version = "resume", "1.0.0"
        self._agent_directory: Any = None
        self._session_index: Any = None
        self._guards = {"_agent_directory": ContractGuard(self, "_agent_directory", AgentDirectoryProvider), "_session_index": ContractGuard(self, "_session_index", SessionIndexProvider)}

    @BindField("_agent_directory", if_valid=True)
    def _bind_agent(self, field: str, service: Any, reference: Any) -> None: self._guards[field].admit(service)
    @UnbindField("_agent_directory", if_valid=True)
    def _unbind_agent(self, field: str, service: Any, reference: Any) -> None: self._guards[field].release(service)
    @BindField("_session_index", if_valid=True)
    def _bind_session(self, field: str, service: Any, reference: Any) -> None: self._guards[field].admit(service)
    @UnbindField("_session_index", if_valid=True)
    def _unbind_session(self, field: str, service: Any, reference: Any) -> None: self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()
        @router.post("/resume")
        async def resume(payload: ResumeRequest = Body(...)) -> StreamingResponse:
            if self._agent_directory is None or self._session_index is None:
                raise HTTPException(503, "Agent services unavailable")
            try:
                user = validate_id(payload.user_id, field="user_id")
                agent = validate_id(payload.agent_id, field="agent_id")
                session = validate_id(payload.session_id, field="session_id")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            loop = self._agent_directory.get_loop(agent)
            if loop is None:
                raise HTTPException(503, "Agent loop unavailable")
            await self._session_index.touch(user, session, agent)
            async def generate() -> AsyncIterator[str]:
                yield json.dumps({"type": "session", "session_id": session, "agent_id": agent, "user_id": user}) + "\n"
                async for event in loop.astream("", thread_id=thread_key(user, session, agent), resume=payload.decision):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            return StreamingResponse(generate(), media_type="application/x-ndjson")
        return router

    def get_plugin_info(self) -> dict[str, str]: return {"name": self._plugin_name, "version": self._plugin_version}
