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
from langharmess_core.contracts import AgentLoopProvider, ModelProtocol
from langharmess_core.plugin import runtime_llm_descriptor
from langharmess_plugin.contracts import PluginRegistrar
from langharmess_plugin.validation import ContractGuard, ContractViolationError

LOGGER = logging.getLogger("langharmess.server")


def _safe_error_message(exc: Exception, api_key: str) -> str:
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "***")
    return message[:2000]


class StreamRequest(BaseModel):
    input: str
    model: str
    api_key: str
    base_url: str
    session_id: str
    stream_usage: bool | None = None
    protocol: ModelProtocol = "chat"


@ComponentFactory("api-stream-route-factory")
@Provides(RouteProvider)
@Property("_plugin_name", "plugin.name", "stream")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_loop", AgentLoopProvider, optional=True, immediate_rebind=True)
@RequiresBest(
    "_plugin_registrar", PluginRegistrar, optional=True, immediate_rebind=True
)
class StreamRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "stream"
        self._plugin_version = "1.0.0"
        self._agent_loop: Any = None
        self._plugin_registrar: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_agent_loop": ContractGuard(self, "_agent_loop", AgentLoopProvider),
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
            except BaseException:
                self._runtime_lock.release()
                raise

            async def generate() -> AsyncIterator[str]:
                try:
                    async for event in self._agent_loop.astream(
                        payload.input, thread_id=payload.session_id
                    ):
                        yield f"{json.dumps(event, ensure_ascii=False)}\n"
                except Exception as exc:
                    LOGGER.exception("Agent stream failed")
                    error = {
                        "type": "error",
                        "error_type": type(exc).__name__,
                        "message": _safe_error_message(exc, payload.api_key),
                    }
                    yield f"{json.dumps(error, ensure_ascii=False)}\n"
                finally:
                    self._runtime_lock.release()

            return StreamingResponse(generate(), media_type="application/x-ndjson")

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
