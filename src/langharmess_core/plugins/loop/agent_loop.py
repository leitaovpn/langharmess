"""Agent loop component assembled from injected plugin services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import ToolMessage
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Invalidate,
    Provides,
    Requires,
    RequiresBest,
    UnbindField,
    Validate,
)

from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_CACHE,
    SPEC_CHECKPOINTER,
    SPEC_CONTEXT_SCHEMA,
    SPEC_DEBUG,
    SPEC_INTERRUPT_AFTER,
    SPEC_INTERRUPT_BEFORE,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_NAME,
    SPEC_RESPONSE_FORMAT,
    SPEC_STATE_SCHEMA,
    SPEC_STORE,
    SPEC_SYSTEM_PROMPT,
    SPEC_TOOL,
    SPEC_TRANSFORMERS,
)


def _extract_usage(message: Any) -> dict[str, int] | None:
    """Return token usage carried by a streamed message chunk, if any."""
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        usage = (getattr(message, "response_metadata", None) or {}).get("token_usage")
    if not usage:
        return None
    extracted = {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
    return extracted if sum(extracted.values()) else None


def _extract_content(message: Any) -> str:
    """Normalize plain and structured LangChain message content to text."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
        )
    return str(content) if content else ""


def _strip_orphan_tool_use(message: Any) -> None:
    """Drop streamed tool_use fragments that never became completable tool calls.

    Anthropic-style streaming keeps every partial ``tool_use`` block in
    ``content`` while only completed calls are parsed into ``tool_calls``.
    Replaying an orphan makes the provider reject the next request because
    every ``tool_use`` id needs a matching ``tool_result``.
    """
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return
    completed_ids = {
        tool_call.get("id") for tool_call in getattr(message, "tool_calls", None) or []
    }
    message.content = [
        block
        for block in content
        if not (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("id") not in completed_ids
        )
    ]


@ComponentFactory("agent-loop-factory")
@Provides(SPEC_AGENT_LOOP)
@RequiresBest("_llm_provider", SPEC_LLM, optional=False, immediate_rebind=True)
@Requires("_tool_providers", SPEC_TOOL, aggregate=True, optional=True)
@Requires("_middleware_providers", SPEC_MIDDLEWARE, aggregate=True, optional=True)
@Requires("_system_prompt_providers", SPEC_SYSTEM_PROMPT, aggregate=True, optional=True)
@RequiresBest(
    "_response_format_provider",
    SPEC_RESPONSE_FORMAT,
    optional=True,
    immediate_rebind=True,
)
@RequiresBest(
    "_state_schema_provider",
    SPEC_STATE_SCHEMA,
    optional=True,
    immediate_rebind=True,
)
@RequiresBest(
    "_context_schema_provider",
    SPEC_CONTEXT_SCHEMA,
    optional=True,
    immediate_rebind=True,
)
@RequiresBest(
    "_checkpointer_provider",
    SPEC_CHECKPOINTER,
    optional=True,
    immediate_rebind=True,
)
@RequiresBest("_store_provider", SPEC_STORE, optional=True, immediate_rebind=True)
@Requires(
    "_interrupt_before_providers",
    SPEC_INTERRUPT_BEFORE,
    aggregate=True,
    optional=True,
)
@Requires(
    "_interrupt_after_providers",
    SPEC_INTERRUPT_AFTER,
    aggregate=True,
    optional=True,
)
@RequiresBest("_debug_provider", SPEC_DEBUG, optional=True, immediate_rebind=True)
@RequiresBest("_name_provider", SPEC_NAME, optional=True, immediate_rebind=True)
@RequiresBest("_cache_provider", SPEC_CACHE, optional=True, immediate_rebind=True)
@Requires(
    "_transformers_providers",
    SPEC_TRANSFORMERS,
    aggregate=True,
    optional=True,
)
class PluginAgentLoop:
    """Rebuilds a LangChain agent graph when injected services change."""

    def __init__(self) -> None:
        self._llm_provider: Any = None
        self._tool_providers: list[Any] = []
        self._middleware_providers: list[Any] = []
        self._system_prompt_providers: list[Any] = []
        self._response_format_provider: Any = None
        self._state_schema_provider: Any = None
        self._context_schema_provider: Any = None
        self._checkpointer_provider: Any = None
        self._store_provider: Any = None
        self._interrupt_before_providers: list[Any] = []
        self._interrupt_after_providers: list[Any] = []
        self._debug_provider: Any = None
        self._name_provider: Any = None
        self._cache_provider: Any = None
        self._transformers_providers: list[Any] = []
        self._graph: Any = None

    @Validate
    def _validate(self, bundle_context: Any) -> None:
        self._rebuild()

    @Invalidate
    def _invalidate(self, bundle_context: Any) -> None:
        self._graph = None

    @BindField("_tool_providers", if_valid=True)
    def _on_tool_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_tool_providers", if_valid=True)
    def _on_tool_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @BindField("_middleware_providers", if_valid=True)
    def _on_middleware_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_middleware_providers", if_valid=True)
    def _on_middleware_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @BindField("_system_prompt_providers", if_valid=True)
    def _on_system_prompt_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_system_prompt_providers", if_valid=True)
    def _on_system_prompt_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @BindField("_response_format_provider", if_valid=True)
    def _on_response_format_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_response_format_provider")
    def _on_response_format_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_state_schema_provider", if_valid=True)
    def _on_state_schema_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_state_schema_provider")
    def _on_state_schema_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_context_schema_provider", if_valid=True)
    def _on_context_schema_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_context_schema_provider")
    def _on_context_schema_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_checkpointer_provider", if_valid=True)
    def _on_checkpointer_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_checkpointer_provider")
    def _on_checkpointer_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_store_provider", if_valid=True)
    def _on_store_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_store_provider")
    def _on_store_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_interrupt_before_providers", if_valid=True)
    def _on_interrupt_before_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_interrupt_before_providers", if_valid=True)
    def _on_interrupt_before_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._rebuild()

    @BindField("_interrupt_after_providers", if_valid=True)
    def _on_interrupt_after_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_interrupt_after_providers", if_valid=True)
    def _on_interrupt_after_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._rebuild()

    @BindField("_debug_provider", if_valid=True)
    def _on_debug_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_debug_provider")
    def _on_debug_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_name_provider", if_valid=True)
    def _on_name_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_name_provider")
    def _on_name_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_cache_provider", if_valid=True)
    def _on_cache_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_cache_provider")
    def _on_cache_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._graph = None

    @BindField("_transformers_providers", if_valid=True)
    def _on_transformers_bind(self, field: str, service: Any, reference: Any) -> None:
        self._rebuild()

    @UnbindField("_transformers_providers", if_valid=True)
    def _on_transformers_unbind(
        self, field: str, service: Any, reference: Any
    ) -> None:
        self._rebuild()

    def _collect_tools(self) -> list[Any]:
        tools: list[Any] = []
        for provider in self._tool_providers or []:
            tools.extend(provider.get_tools())
        return tools

    def _collect_middlewares(self) -> list[Any]:
        middlewares: list[Any] = []
        for provider in self._middleware_providers or []:
            middlewares.extend(provider.get_middlewares())
        return middlewares

    def _collect_system_prompt(self) -> str | None:
        parts = [
            provider.get_system_prompt()
            for provider in self._system_prompt_providers or []
        ]
        parts = [part for part in parts if part]
        if not parts:
            return None
        return "\n".join(parts)

    def _collect_interrupt_before(self) -> list[str]:
        values: list[str] = []
        for provider in self._interrupt_before_providers or []:
            values.extend(provider.get_interrupt_before())
        return values

    def _collect_interrupt_after(self) -> list[str]:
        values: list[str] = []
        for provider in self._interrupt_after_providers or []:
            values.extend(provider.get_interrupt_after())
        return values

    def _collect_transformers(self) -> list[Any]:
        values: list[Any] = []
        for provider in self._transformers_providers or []:
            values.extend(provider.get_transformers())
        return values

    def _rebuild(self) -> None:
        model = self._llm_provider.get_model() if self._llm_provider else None
        if model is None:
            self._graph = None
            return
        self._graph = create_agent(
            model,
            tools=self._collect_tools(),
            middleware=self._collect_middlewares(),
            system_prompt=self._collect_system_prompt(),
            response_format=(
                self._response_format_provider.get_response_format()
                if self._response_format_provider
                else None
            ),
            state_schema=(
                self._state_schema_provider.get_state_schema()
                if self._state_schema_provider
                else None
            ),
            context_schema=(
                self._context_schema_provider.get_context_schema()
                if self._context_schema_provider
                else None
            ),
            checkpointer=(
                self._checkpointer_provider.get_checkpointer()
                if self._checkpointer_provider
                else None
            ),
            store=self._store_provider.get_store() if self._store_provider else None,
            interrupt_before=self._collect_interrupt_before() or None,
            interrupt_after=self._collect_interrupt_after() or None,
            debug=self._debug_provider.get_debug() if self._debug_provider else False,
            name=self._name_provider.get_name() if self._name_provider else None,
            cache=self._cache_provider.get_cache() if self._cache_provider else None,
            transformers=self._collect_transformers() or None,
        )

    def invoke(self, message: str, *, thread_id: str | None = None) -> Any:
        if self._graph is None:
            raise RuntimeError("Agent graph is not built; no LLM plugin is available")
        config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        return self._graph.invoke(
            {"messages": [{"role": "user", "content": message}]}, config=config
        )

    async def astream(
        self, message: str, *, thread_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        if self._graph is None:
            raise RuntimeError("Agent graph is not built; no LLM plugin is available")
        config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        previous_content: dict[str, str] = {}
        usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        async for stream_type, chunk in self._graph.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if stream_type == "messages":
                streamed_message = chunk[0]
                usage = _extract_usage(streamed_message)
                if usage is not None:
                    for key in usage_totals:
                        usage_totals[key] += usage[key]
                if isinstance(streamed_message, ToolMessage):
                    continue
                if getattr(streamed_message, "tool_calls", None) or getattr(
                    streamed_message, "tool_call_chunks", None
                ):
                    continue
                content = _extract_content(streamed_message)
                message_id = str(getattr(streamed_message, "id", None) or "default")
                previous = previous_content.get(message_id, "")
                delta = content[len(previous) :] if content.startswith(previous) else content
                previous_content[message_id] = content
                if delta:
                    yield {"type": "assistant", "content": delta}
                continue

            for update in chunk.values():
                if update is None:
                    continue
                for updated_message in update.get("messages", []):
                    _strip_orphan_tool_use(updated_message)
                    if isinstance(updated_message, ToolMessage):
                        yield {
                            "type": "tool_output",
                            "name": updated_message.name or "tool",
                            "tool_call_id": updated_message.tool_call_id,
                            "output": str(updated_message.content),
                        }
                    for tool_call in getattr(updated_message, "tool_calls", []):
                        yield {
                            "type": "tool_call",
                            "name": tool_call["name"],
                            "tool_call_id": tool_call["id"],
                            "args": tool_call["args"],
                        }
        if usage_totals["total_tokens"]:
            yield {"type": "usage", **usage_totals}

    def describe(self) -> dict[str, Any]:
        llm_info = self._llm_provider.get_plugin_info() if self._llm_provider else None
        return {
            "llm": llm_info,
            "tools": [getattr(tool, "name", str(tool)) for tool in self._collect_tools()],
            "middleware": [middleware.name for middleware in self._collect_middlewares()],
        }
