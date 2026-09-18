"""Agent loop component that assembles the LangChain graph from plugins."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Provides,
    Requires,
    RequiresBest,
    UnbindField,
    Validate,
)

from langharness_plugin.validation import ContractGuard
from plugin_demo.contracts import (
    SPEC_AGENT_LOOP,
    LLMProvider,
    MiddlewareProvider,
    ToolProvider,
)


@ComponentFactory("agent-loop-factory")
@Instantiate("agent-loop")
@Provides(SPEC_AGENT_LOOP)
@RequiresBest("_llm_provider", LLMProvider, optional=False, immediate_rebind=True)
@Requires("_tool_providers", ToolProvider, aggregate=True, optional=True)
@Requires("_middleware_providers", MiddlewareProvider, aggregate=True, optional=True)
class PluginAgentLoop:
    """Rebuilds a LangChain ``create_agent`` graph when plugin services change."""

    def __init__(self):
        self._llm_provider = None
        self._tool_providers = []
        self._middleware_providers = []
        self._guards = {
            "_llm_provider": ContractGuard(self, "_llm_provider", LLMProvider),
            "_tool_providers": ContractGuard(self, "_tool_providers", ToolProvider),
            "_middleware_providers": ContractGuard(
                self, "_middleware_providers", MiddlewareProvider
            ),
        }
        self._graph = None

    @Validate
    def _validate(self, bundle_context):
        self._rebuild()

    @Invalidate
    def _invalidate(self, bundle_context):
        self._graph = None

    @BindField("_llm_provider", if_valid=True)
    def _on_llm_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guards[field].admit(service):
            self._graph = None
            return
        self._rebuild()

    @UnbindField("_llm_provider", if_valid=True)
    def _on_llm_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)
        self._graph = None

    @BindField("_tool_providers", if_valid=True)
    def _on_tool_bind(self, field, service, reference):
        if not self._guards[field].admit(service):
            return
        self._rebuild()

    @UnbindField("_tool_providers", if_valid=True)
    def _on_tool_unbind(self, field, service, reference):
        self._guards[field].release(service)
        self._rebuild()

    @BindField("_middleware_providers", if_valid=True)
    def _on_middleware_bind(self, field, service, reference):
        if not self._guards[field].admit(service):
            return
        self._rebuild()

    @UnbindField("_middleware_providers", if_valid=True)
    def _on_middleware_unbind(self, field, service, reference):
        self._guards[field].release(service)
        self._rebuild()

    def _collect_tools(self):
        tools = []
        for provider in self._tool_providers or []:
            tools.extend(provider.get_tools())
        return tools

    def _collect_middlewares(self):
        middlewares = []
        for provider in self._middleware_providers or []:
            middlewares.extend(provider.get_middlewares())
        return middlewares

    def _rebuild(self):
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

    def invoke(self, message: str):
        if self._graph is None:
            raise RuntimeError("Agent graph is not built; no LLM plugin is available")
        return self._graph.invoke({"messages": [{"role": "user", "content": message}]})

    def describe(self):
        llm_info = self._llm_provider.get_plugin_info() if self._llm_provider else None
        return {
            "llm": llm_info,
            "tools": [
                getattr(tool, "name", str(tool)) for tool in self._collect_tools()
            ],
            "middleware": [
                middleware.name for middleware in self._collect_middlewares()
            ],
        }
