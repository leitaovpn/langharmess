"""Unit tests for concrete plugin component methods."""
# mypy: ignore-errors

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import StructuredTool

import langharmess_core.plugins.loop.llm.llm as llm_module
from langharmess_core.agent_loop import PluginAgentLoop
from langharmess_core.plugins.loop.llm.llm import LLMPlugin
from langharmess_core.plugins.loop.middleware.template_middleware import (
    TemplateMiddlewarePlugin,
)
from langharmess_core.plugins.loop.tools.tools import ToolPlugin


def test_llm_plugin_uses_injected_model_instance() -> None:
    model = FakeListChatModel(responses=["hello"])
    plugin = LLMPlugin()
    plugin._model_instance = model
    assert plugin.get_model() is model
    assert plugin.get_plugin_info() == {"name": "llm-plugin", "version": "1.0.0"}


def test_llm_plugin_uses_model_name() -> None:
    plugin = LLMPlugin()
    plugin._model_instance = None
    plugin._model_name = "fake"
    sentinel = object()
    original = llm_module.init_chat_model
    llm_module.init_chat_model = lambda name: sentinel
    try:
        assert plugin.get_model() is sentinel
    finally:
        llm_module.init_chat_model = original


def test_llm_plugin_defaults_to_openai_model() -> None:
    plugin = LLMPlugin()
    plugin._model_instance = None
    plugin._model_name = ""
    sentinel = object()
    original = llm_module.ChatOpenAI
    llm_module.ChatOpenAI = lambda **kwargs: sentinel
    try:
        assert plugin.get_model() is sentinel
    finally:
        llm_module.ChatOpenAI = original


def test_tool_plugin_wraps_callables() -> None:
    plugin = ToolPlugin()
    plugin._tool_functions = None
    tools = plugin.get_tools()
    assert tools and tools[0].name == "add"


def test_tool_plugin_keeps_existing_base_tools() -> None:
    def echo(x: str) -> str:
        """Return the input unchanged."""
        return x

    existing = StructuredTool.from_function(func=echo, name="echo")
    plugin = ToolPlugin()
    plugin._tool_functions = [existing]
    assert plugin.get_tools() == [existing]


def test_tool_plugin_wraps_raw_callable_and_exposes_info() -> None:
    def multiply(x: int, y: int) -> int:
        """Multiply two integers."""
        return x * y

    plugin = ToolPlugin()
    plugin._tool_functions = [multiply]
    tools = plugin.get_tools()
    assert tools[0].name == "multiply"
    assert plugin.get_plugin_info() == {"name": "tools-plugin", "version": "1.0.0"}


def test_middleware_plugin_returns_unique_named_middleware() -> None:
    plugin = TemplateMiddlewarePlugin()
    plugin._plugin_name = "test-middleware"
    middlewares = plugin.get_middlewares()
    assert len(middlewares) == 1
    assert middlewares[0].name == "test-middleware"
    assert plugin.get_plugin_info() == {
        "name": "test-middleware",
        "version": "1.0.0",
    }


def test_agent_loop_rebuild_without_llm_is_safe() -> None:
    loop = PluginAgentLoop()
    loop._llm_provider = None
    loop._tool_providers = []
    loop._middleware_providers = []
    loop._graph = object()
    loop._rebuild()
    assert loop._graph is None
    with pytest.raises(RuntimeError):
        loop.invoke("hello")
    assert loop.describe()["llm"] is None
