"""Unit tests for concrete plugin component methods."""
# mypy: ignore-errors

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import StructuredTool

import langharness_core.plugins.llm.llm as llm_module
from langharness_core.plugins.llm.llm import LLMPlugin
from langharness_core.plugins.loop.agent_loop import PluginAgentLoop
from langharness_core.plugins.middleware.human_approval import HumanApprovalPlugin
from langharness_core.plugins.middleware.template_middleware import (
    TemplateMiddlewarePlugin,
)
from langharness_core.plugins.tools.tools import ToolPlugin
from langharness_core.plugins.tools.workspace import WorkspaceToolsPlugin


def test_llm_plugin_uses_injected_model_instance() -> None:
    model = FakeListChatModel(responses=["hello"])
    plugin = LLMPlugin()
    plugin._model_instance = model
    assert plugin.get_model() is model
    assert plugin.get_protocol() == "chat"
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


def test_llm_plugin_uses_openai_compatible_configuration() -> None:
    plugin = LLMPlugin()
    plugin._model_name = "custom-model"
    plugin._api_key = "secret"
    plugin._base_url = "https://models.example/v1"
    captured = {}
    original = llm_module.ChatOpenAI
    llm_module.ChatOpenAI = lambda **kwargs: captured.update(kwargs) or object()
    try:
        plugin.get_model()
    finally:
        llm_module.ChatOpenAI = original
    assert captured["model"] == "custom-model"
    assert captured["api_key"].get_secret_value() == "secret"
    assert captured["base_url"] == "https://models.example/v1"
    assert captured["stream_usage"] is True
    assert captured["use_responses_api"] is False


def test_llm_plugin_uses_responses_protocol() -> None:
    plugin = LLMPlugin()
    plugin._protocol = "responses"
    plugin._model_name = "gpt-test"
    captured = {}
    original = llm_module.ChatOpenAI
    llm_module.ChatOpenAI = lambda **kwargs: captured.update(kwargs) or object()
    try:
        plugin.get_model()
    finally:
        llm_module.ChatOpenAI = original
    assert captured["use_responses_api"] is True
    assert captured["model"] == "gpt-test"


def test_llm_plugin_uses_anthropic_protocol() -> None:
    plugin = LLMPlugin()
    plugin._protocol = "anthropic"
    plugin._model_name = "claude-test"
    plugin._api_key = "secret"
    plugin._base_url = "https://anthropic.example"
    captured = {}
    original = llm_module.ChatAnthropic
    llm_module.ChatAnthropic = lambda **kwargs: captured.update(kwargs) or object()
    try:
        plugin.get_model()
    finally:
        llm_module.ChatAnthropic = original
    assert captured["model_name"] == "claude-test"
    assert captured["api_key"].get_secret_value() == "secret"
    assert captured["base_url"] == "https://anthropic.example"


def test_llm_plugin_rejects_unknown_protocol() -> None:
    plugin = LLMPlugin()
    plugin._protocol = "invalid"
    with pytest.raises(ValueError, match="Unsupported LLM protocol"):
        plugin.get_model()


def test_llm_plugin_stream_usage_can_be_disabled() -> None:
    plugin = LLMPlugin()
    plugin._model_name = "custom-model"
    plugin._api_key = "secret"
    plugin._base_url = "https://models.example/v1"
    plugin._stream_usage = False
    captured = {}
    original = llm_module.ChatOpenAI
    llm_module.ChatOpenAI = lambda **kwargs: captured.update(kwargs) or object()
    try:
        plugin.get_model()
    finally:
        llm_module.ChatOpenAI = original
    assert captured["stream_usage"] is False


def test_llm_plugin_passes_stream_usage_to_init_chat_model_models() -> None:
    from types import SimpleNamespace

    plugin = LLMPlugin()
    plugin._model_instance = None
    plugin._model_name = "fake"
    model = SimpleNamespace(stream_usage=False)
    original = llm_module.init_chat_model
    llm_module.init_chat_model = lambda name: model
    try:
        assert plugin.get_model() is model
    finally:
        llm_module.init_chat_model = original
    assert model.stream_usage is True


def test_llm_plugin_defaults_to_openai_model() -> None:
    plugin = LLMPlugin()
    plugin._model_instance = None
    plugin._model_name = ""
    sentinel = object()
    captured = {}
    original = llm_module.ChatOpenAI
    llm_module.ChatOpenAI = lambda **kwargs: captured.update(kwargs) or sentinel
    try:
        assert plugin.get_model() is sentinel
    finally:
        llm_module.ChatOpenAI = original
    assert captured["stream_usage"] is True


def test_tool_plugin_wraps_callables() -> None:
    plugin = ToolPlugin()
    plugin._tool_functions = None
    tools = plugin.get_tools()
    assert tools and tools[0].name == "add"


def test_workspace_tools_plugin_provides_file_and_bash_tools(tmp_path) -> None:
    plugin = WorkspaceToolsPlugin()
    plugin._root_dir = str(tmp_path)
    tools = {tool.name: tool for tool in plugin.get_tools()}

    assert {"read_file", "write_file", "list_directory", "bash"} <= tools.keys()
    assert "workspace-ok" in tools["bash"].invoke({"commands": "printf workspace-ok"})
    assert plugin.get_plugin_info() == {
        "name": "workspace-tools",
        "version": "1.0.0",
    }


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
    assert plugin.get_plugin_info() == {"name": "test-middleware", "version": "1.0.0"}


def test_human_approval_plugin_only_interrupts_configured_tools() -> None:
    plugin = HumanApprovalPlugin()
    assert plugin.get_middlewares() == []
    plugin._dangerous_tools = ["bash", "write_file"]
    middleware = plugin.get_middlewares()[0]
    assert middleware.interrupt_on == {
        "bash": {"allowed_decisions": ["approve", "edit", "reject", "respond"]},
        "write_file": {"allowed_decisions": ["approve", "edit", "reject", "respond"]},
    }
    assert plugin.get_plugin_info() == {
        "name": "human-approval-plugin",
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
