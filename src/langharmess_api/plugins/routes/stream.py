"""Streaming agent route plugin."""

from __future__ import annotations

import asyncio
import json
import logging
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

from langharmess_api.contracts import RouteProvider
from langharmess_core.common.ids import thread_key, validate_id
from langharmess_core.contracts import (
    AgentLoopProvider,
    AgentRegistryProvider,
    ModelProtocol,
    SessionIndexProvider,
)
from langharmess_core.plugin import runtime_llm_descriptor
from langharmess_plugin.contracts import PluginRegistrar
from langharmess_plugin.validation import ContractGuard, ContractViolationError

LOGGER = logging.getLogger("langharmess.server")


def _safe_error_message(exc: Exception, api_key: str) -> str:
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "***")
    return message[:2000]


def _encode(event: dict[str, Any]) -> str:
    return f"{json.dumps(event, ensure_ascii=False)}\n"


class StreamRequest(BaseModel):
    input: str
    model: str | None = None
    api_key: str = ""
    base_url: str = ""
    session_id: str | None = None
    user_id: str = "local_user"
    agent_id: str = "simple_agent"
    stream_usage: bool | None = None
    protocol: ModelProtocol = "chat"


@ComponentFactory("api-stream-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "stream")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_loop", AgentLoopProvider, optional=True, immediate_rebind=True)
@RequiresBest(
    "_agent_registry", AgentRegistryProvider, optional=True, immediate_rebind=True
)
@RequiresBest(
    "_session_index", SessionIndexProvider, optional=True, immediate_rebind=True
)
@RequiresBest(
    "_plugin_registrar", PluginRegistrar, optional=True, immediate_rebind=True
)
class StreamRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "stream"
        self._plugin_version = "1.0.0"
        self._agent_loop: Any = None
        self._agent_registry: Any = None
        self._session_index: Any = None
        self._plugin_registrar: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_agent_loop": ContractGuard(self, "_agent_loop", AgentLoopProvider),
            "_agent_registry": ContractGuard(
                self, "_agent_registry", AgentRegistryProvider
            ),
            "_session_index": ContractGuard(
                self, "_session_index", SessionIndexProvider
            ),
            "_plugin_registrar": ContractGuard(
                self, "_plugin_registrar", PluginRegistrar
            ),
        }
        self._runtime_lock = asyncio.Lock()

    @BindField("_agent_loop", if_valid=True)
    def _on_agent_loop_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_agent_loop", if_valid=True)
    def _on_agent_loop_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    @BindField("_agent_registry", if_valid=True)
    def _on_agent_registry_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_agent_registry", if_valid=True)
    def _on_agent_registry_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    @BindField("_session_index", if_valid=True)
    def _on_session_index_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_session_index", if_valid=True)
    def _on_session_index_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    @BindField("_plugin_registrar", if_valid=True)
    def _on_plugin_registrar_bind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].admit(service)

    @UnbindField("_plugin_registrar", if_valid=True)
    def _on_plugin_registrar_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].release(service)

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/stream")
        async def stream(payload: StreamRequest = Body(...)) -> StreamingResponse:
            if self._plugin_registrar is None:
                raise HTTPException(
                    status_code=503, detail="Plugin registrar unavailable"
                )

            await self._runtime_lock.acquire()
            try:
                user_id, agent_id, session_id = self._resolve_identity(payload)
                self._require_agent(agent_id)
                if payload.model is None:
                    raise HTTPException(
                        status_code=400,
                        detail="model is required until agents own their llm",
                    )
                properties: dict[str, Any] = {
                    "plugin.model.name": payload.model,
                    "plugin.model.api_key": payload.api_key,
                    "plugin.model.base_url": payload.base_url,
                    "plugin.model.protocol": payload.protocol,
                }
                if payload.stream_usage is not None:
                    properties["plugin.model.stream_usage"] = payload.stream_usage
                try:
                    self._plugin_registrar.ensure_plugin(
                        runtime_llm_descriptor(properties)
                    )
                except ContractViolationError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                if self._agent_loop is None:
                    raise HTTPException(status_code=503, detail="Agent loop unavailable")
                session_id = await self._ensure_session(user_id, session_id)
                await self._session_index.touch(user_id, session_id, agent_id)
            except BaseException:
                self._runtime_lock.release()
                raise

            async def generate() -> AsyncIterator[str]:
                try:
                    yield _encode(
                        {
                            "type": "session",
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "user_id": user_id,
                        }
                    )
                    async for event in self._agent_loop.astream(
                        payload.input, thread_id=thread_key(user_id, session_id)
                    ):
                        yield _encode(event)
                except Exception as exc:
                    LOGGER.exception("Agent stream failed")
                    yield _encode(
                        {
                            "type": "error",
                            "error_type": type(exc).__name__,
                            "message": _safe_error_message(exc, payload.api_key),
                        }
                    )
                finally:
                    self._runtime_lock.release()

            return StreamingResponse(generate(), media_type="application/x-ndjson")

        return router

    def _resolve_identity(self, payload: StreamRequest) -> tuple[str, str, str | None]:
        try:
            user_id = validate_id(payload.user_id, field="user_id")
            agent_id = validate_id(payload.agent_id, field="agent_id")
            session_id = (
                validate_id(payload.session_id, field="session_id")
                if payload.session_id is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return user_id, agent_id, session_id

    def _require_agent(self, agent_id: str) -> None:
        if self._agent_registry is None:
            raise HTTPException(status_code=503, detail="Agent registry unavailable")
        agent = self._agent_registry.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_id}")
        if not agent.get("enabled", False):
            raise HTTPException(status_code=400, detail=f"Agent is disabled: {agent_id}")

    async def _ensure_session(self, user_id: str, session_id: str | None) -> str:
        if self._session_index is None:
            raise HTTPException(status_code=503, detail="Session index unavailable")
        if session_id is None:
            created: Any = await self._session_index.new_session(user_id)
            return str(created)
        return session_id

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
