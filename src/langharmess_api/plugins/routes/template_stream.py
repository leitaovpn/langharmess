"""Stream route plugin template."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, RequiresBest

from langharmess_api.contracts import SPEC_ROUTE
from langharmess_core.contracts import SPEC_AGENT_LOOP


@ComponentFactory("api-stream-route-template-factory")
@Provides(SPEC_ROUTE)
@Property("_plugin_name", "plugin.name", "template-stream")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest("_agent_loop", SPEC_AGENT_LOOP, optional=True, immediate_rebind=True)
class TemplateStreamRoutePlugin:
    def __init__(self) -> None:
        self._plugin_name = "template-stream"
        self._plugin_version = "1.0.0"
        self._agent_loop: Any = None

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/stream")
        async def stream(payload: dict[str, str] = Body(...)) -> StreamingResponse:
            if self._agent_loop is None:
                raise HTTPException(status_code=503, detail="Agent loop unavailable")

            async def generate() -> AsyncIterator[str]:
                async for text in self._agent_loop.astream(payload["input"]):
                    yield f"{text}\n"

            return StreamingResponse(generate(), media_type="text/plain")

        return router

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
