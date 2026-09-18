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
    AgentDirectoryProvider,
    ModelProtocol,
    SessionIndexProvider,
)
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
    input: str = ""
    decision: str | dict[str, Any] | None = None
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
@RequiresBest(
    "_agent_directory", AgentDirectoryProvider, optional=True, immediate_rebind=True
)
@RequiresBest(
    "_session_index", SessionIndexProvider, optional=True, immediate_rebind=True
)
class StreamRoutePlugin:
    """Streams one agent turn; configuration changes, streaming stays unlocked."""

    def __init__(self) -> None:
        self._plugin_name = "stream"
        self._plugin_version = "1.0.0"
        self._agent_directory: Any = None
        self._session_index: Any = None
        self._guards: dict[str, ContractGuard] = {
            "_agent_directory": ContractGuard(
                self, "_agent_directory", AgentDirectoryProvider
            ),
            "_session_index": ContractGuard(
                self, "_session_index", SessionIndexProvider
            ),
        }
        self._configuration_lock = asyncio.Lock()

    @BindField("_agent_directory", if_valid=True)
    def _on_agent_directory_bind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._guards[field].admit(service)

    @UnbindField("_agent_directory", if_valid=True)
    def _on_agent_directory_unbind(
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

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/stream")
        async def stream(payload: StreamRequest = Body(...)) -> StreamingResponse:
            if self._agent_directory is None:
                raise HTTPException(
                    status_code=503, detail="Agent directory unavailable"
                )

            user_id, agent_id, session_id = self._resolve_identity(payload)
            if payload.model is None and not self._agent_directory.binding_properties(
                agent_id, "llm"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="model is required until the agent configures its llm",
                )

            async with self._configuration_lock:
                self._apply_agent_configuration(agent_id, payload)

            loop = self._agent_directory.get_loop(agent_id)
            if loop is None:
                raise HTTPException(status_code=503, detail="Agent loop unavailable")

            session_id = await self._ensure_session(user_id, session_id)
            await self._session_index.touch(user_id, session_id, agent_id)

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
                    kwargs: dict[str, Any] = {"thread_id": thread_key(user_id, session_id, agent_id)}
                    if payload.decision is not None:
                        kwargs["resume"] = payload.decision
                    async for event in loop.astream(payload.input, **kwargs):
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

            return StreamingResponse(generate(), media_type="application/x-ndjson")

        return router

    def _apply_agent_configuration(self, agent_id: str, payload: StreamRequest) -> None:
        properties: dict[str, Any] = {}
        if payload.model is not None:
            properties["plugin.model.name"] = payload.model
            properties["plugin.model.protocol"] = payload.protocol
        if payload.api_key:
            properties["plugin.model.api_key"] = payload.api_key
        if payload.base_url:
            properties["plugin.model.base_url"] = payload.base_url
        if payload.stream_usage is not None:
            properties["plugin.model.stream_usage"] = payload.stream_usage
        try:
            self._agent_directory.ensure_plugin_instance(agent_id, "llm", properties)
        except ContractViolationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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

    async def _ensure_session(self, user_id: str, session_id: str | None) -> str:
        if self._session_index is None:
            raise HTTPException(status_code=503, detail="Session index unavailable")
        if session_id is None:
            created: Any = await self._session_index.new_session(user_id)
            return str(created)
        return session_id

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
