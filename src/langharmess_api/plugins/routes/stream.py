"""Streaming agent route plugin."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, RequiresBest
from pydantic import BaseModel

from langharmess_api.contracts import SPEC_ROUTE
from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_LLM
from langharmess_plugin.contracts import SPEC_PLUGIN_REGISTRAR
from langharmess_plugin.registry import PluginDescriptor


class StreamRequest(BaseModel):
    input: str
    model: str
    api_key: str
    base_url: str
    session_id: str
    stream_usage: bool | None = None


@ComponentFactory("api-stream-route-factory")
@Provides(SPEC_ROUTE)
@Property("_plugin_name", "plugin.name", "stream")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_loop", SPEC_AGENT_LOOP, optional=True, immediate_rebind=True)
@RequiresBest(
    "_plugin_registrar", SPEC_PLUGIN_REGISTRAR, optional=True, immediate_rebind=True
)
class StreamRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "stream"
        self._plugin_version = "1.0.0"
        self._agent_loop: Any = None
        self._plugin_registrar: Any = None

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/stream")
        async def stream(payload: StreamRequest = Body(...)) -> StreamingResponse:
            if self._plugin_registrar is None:
                raise HTTPException(status_code=503, detail="Plugin registrar unavailable")

            properties: dict[str, Any] = {
                "plugin.model.name": payload.model,
                "plugin.model.api_key": payload.api_key,
                "plugin.model.base_url": payload.base_url,
            }
            if payload.stream_usage is not None:
                properties["plugin.model.stream_usage"] = payload.stream_usage
            self._plugin_registrar.ensure_plugin(
                PluginDescriptor(
                    name="runtime-llm",
                    version="1.0.0",
                    module="langharmess_core.plugins.loop.llm.llm",
                    factory="llm-plugin-factory",
                    instance="runtime-llm",
                    specification=SPEC_LLM,
                    ranking=1000,
                    properties=properties,
                )
            )
            if self._agent_loop is None:
                raise HTTPException(status_code=503, detail="Agent loop unavailable")

            async def generate() -> AsyncIterator[str]:
                async for event in self._agent_loop.astream(
                    payload.input, thread_id=payload.session_id
                ):
                    yield f"{json.dumps(event, ensure_ascii=False)}\n"

            return StreamingResponse(
                generate(), media_type="application/x-ndjson"
            )

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
