"""Stream route plugin template."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, RequiresBest
from pydantic import BaseModel, Field

from langharmess_api.contracts import SPEC_ROUTE
from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_LLM
from langharmess_plugin.contracts import SPEC_PLUGIN_REGISTRAR
from langharmess_plugin.registry import PluginDescriptor


class StreamRequest(BaseModel):
    input: str
    model: str
    api_key: str
    base_url: str
    messages: list[dict[str, str]] = Field(default_factory=list)


@ComponentFactory("api-stream-route-template-factory")
@Provides(SPEC_ROUTE)
@Property("_plugin_name", "plugin.name", "template-stream")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_loop", SPEC_AGENT_LOOP, optional=True, immediate_rebind=True)
@RequiresBest(
    "_plugin_registrar", SPEC_PLUGIN_REGISTRAR, optional=True, immediate_rebind=True
)
class TemplateStreamRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "template-stream"
        self._plugin_version = "1.0.0"
        self._agent_loop: Any = None
        self._plugin_registrar: Any = None

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/stream")
        async def stream(payload: StreamRequest = Body(...)) -> StreamingResponse:
            if self._plugin_registrar is None:
                raise HTTPException(status_code=503, detail="Plugin registrar unavailable")

            self._plugin_registrar.ensure_plugin(
                PluginDescriptor(
                    name="runtime-llm",
                    version="1.0.0",
                    module="langharmess_core.plugins.loop.llm.llm",
                    factory="llm-plugin-factory",
                    instance="runtime-llm",
                    specification=SPEC_LLM,
                    ranking=1000,
                    properties={
                        "plugin.model.name": payload.model,
                        "plugin.model.api_key": payload.api_key,
                        "plugin.model.base_url": payload.base_url,
                    },
                )
            )
            if self._agent_loop is None:
                raise HTTPException(status_code=503, detail="Agent loop unavailable")

            async def generate() -> AsyncIterator[str]:
                agent_input = payload.messages or payload.input
                async for text in self._agent_loop.astream(agent_input):
                    yield text

            return StreamingResponse(generate(), media_type="text/plain")

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
