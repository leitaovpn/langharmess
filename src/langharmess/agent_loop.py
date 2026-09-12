"""Agent loop component assembled from injected plugin services."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
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

from langharmess.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_TOOL,
)


@ComponentFactory("agent-loop-factory")
@Provides(SPEC_AGENT_LOOP)
@RequiresBest("_llm_provider", SPEC_LLM, optional=False, immediate_rebind=True)
@Requires("_tool_providers", SPEC_TOOL, aggregate=True, optional=True)
@Requires("_middleware_providers", SPEC_MIDDLEWARE, aggregate=True, optional=True)
class PluginAgentLoop:
    """Rebuilds a LangChain agent graph when injected services change."""

    def __init__(self) -> None:
        self._llm_provider: Any = None
        self._tool_providers: list[Any] = []
        self._middleware_providers: list[Any] = []
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

    def _rebuild(self) -> None:
        model = self._llm_provider.get_model() if self._llm_provider else None
        if model is None:
            self._graph = None
            return
        self._graph = create_agent(
            model,
            tools=self._collect_tools(),
            middleware=self._collect_middlewares(),
            system_prompt="You are a helpful plugin-driven agent.",
        )

    def invoke(self, message: str) -> Any:
        if self._graph is None:
            raise RuntimeError("Agent graph is not built; no LLM plugin is available")
        return self._graph.invoke({"messages": [{"role": "user", "content": message}]})

    def describe(self) -> dict[str, Any]:
        llm_info = self._llm_provider.get_plugin_info() if self._llm_provider else None
        return {
            "llm": llm_info,
            "tools": [getattr(tool, "name", str(tool)) for tool in self._collect_tools()],
            "middleware": [middleware.name for middleware in self._collect_middlewares()],
        }
