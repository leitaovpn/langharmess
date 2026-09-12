"""End-to-end tests that start the real Pelix/iPOPO framework."""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import langharmess.agent_loop as agent_loop_module
from langharmess.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_CACHE,
    SPEC_CHECKPOINTER,
    SPEC_CONTEXT_SCHEMA,
    SPEC_DEBUG,
    SPEC_INTERRUPT_AFTER,
    SPEC_INTERRUPT_BEFORE,
    SPEC_NAME,
    SPEC_RESPONSE_FORMAT,
    SPEC_STATE_SCHEMA,
    SPEC_STORE,
    SPEC_SYSTEM_PROMPT,
    SPEC_TRANSFORMERS,
)
from langharmess.plugin_manager import PluginManager
from langharmess.registry import PluginDescriptor, PluginRegistry

CAPTURED_MESSAGES: list[list] = []


class ScriptedToolCallModel(BaseChatModel):
    responses: list[AIMessage]
    i: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        CAPTURED_MESSAGES.append([message for message in messages])
        response = self.responses[self.i]
        self.i = (self.i + 1) % len(self.responses)
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-call-model"

    def bind_tools(self, tools, **kwargs):
        return self


def scripted_tool_call_model() -> ScriptedToolCallModel:
    return ScriptedToolCallModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 2, "b": 3},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The answer is 5."),
        ]
    )


def descriptors(tmp_path: Path) -> PluginRegistry:
    model = scripted_tool_call_model()
    registry = PluginRegistry(
        [
            PluginDescriptor(
                name="llm",
                version="1.0.0",
                module="langharmess.plugins.llm",
                factory="llm-plugin-factory",
                instance="llm",
                specification="agent.plugin.llm",
                ranking=100,
                properties={"plugin.model.instance": model},
            ),
            PluginDescriptor(
                name="tools",
                version="1.0.0",
                module="langharmess.plugins.tools",
                factory="tools-plugin-factory",
                instance="tools",
                specification="agent.plugin.tools",
            ),
            PluginDescriptor(
                name="middleware",
                version="1.0.0",
                module="langharmess.plugins.middleware",
                factory="middleware-plugin-factory",
                instance="middleware",
                specification="agent.plugin.middleware",
            ),
            PluginDescriptor(
                name="system-prompt-a",
                version="1.0.0",
                module="langharmess.plugins.system_prompt",
                factory="system-prompt-plugin-factory",
                instance="system-prompt-a",
                specification=SPEC_SYSTEM_PROMPT,
                properties={"plugin.system_prompt": "You are A."},
            ),
            PluginDescriptor(
                name="system-prompt-b",
                version="1.0.0",
                module="langharmess.plugins.system_prompt",
                factory="system-prompt-plugin-factory",
                instance="system-prompt-b",
                specification=SPEC_SYSTEM_PROMPT,
                properties={"plugin.system_prompt": "You are B."},
            ),
            PluginDescriptor(
                name="agent-loop",
                version="1.0.0",
                module="langharmess.agent_loop",
                factory="agent-loop-factory",
                instance="agent-loop",
                specification=SPEC_AGENT_LOOP,
            ),
        ]
    )
    return registry


def test_plugin_lifecycle_and_agent_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = descriptors(tmp_path)
    CAPTURED_MESSAGES.clear()
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)

        loop = manager.get_service(SPEC_AGENT_LOOP)
        assert loop.describe()["tools"] == ["add"]

        result = loop.invoke("What is 2 + 3?")
        assert result["messages"][-1].content == "The answer is 5."
        assert isinstance(CAPTURED_MESSAGES[0][0], SystemMessage)
        assert CAPTURED_MESSAGES[0][0].content == "You are A.\nYou are B."

        llm_props = manager.service_properties("agent.plugin.llm")
        assert llm_props[0]["plugin.version"] == "1.0.0"
        assert manager.get_service("agent.plugin.llm").get_plugin_info()["version"] == "1.0.0"

        manager.unbind_plugin("tools")
        assert loop.describe()["tools"] == []

        manager.bind_plugin("tools")
        assert loop.describe()["tools"] == ["add"]

        manager.uninstall_plugin("middleware")
        assert manager.installed_names() == {
            "llm",
            "tools",
            "agent-loop",
            "system-prompt-a",
            "system-prompt-b",
        }

        captured_kwargs: dict[str, object] = {}

        def fake_create_agent(model, tools=None, *, system_prompt=None, **kwargs):
            captured_kwargs["model"] = model
            captured_kwargs["tools"] = tools
            captured_kwargs["system_prompt"] = system_prompt
            captured_kwargs.update(kwargs)
            return object()

        monkeypatch.setattr(agent_loop_module, "create_agent", fake_create_agent)

        response_format = object()
        state_schema = object()
        context_schema = object()
        checkpointer = object()
        store = object()
        cache = object()

        parameter_descriptors = [
            PluginDescriptor(
                name="response-format",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="response-format-plugin-factory",
                instance="response-format",
                specification=SPEC_RESPONSE_FORMAT,
                properties={"plugin.response_format": response_format},
            ),
            PluginDescriptor(
                name="state-schema",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="state-schema-plugin-factory",
                instance="state-schema",
                specification=SPEC_STATE_SCHEMA,
                properties={"plugin.state_schema": state_schema},
            ),
            PluginDescriptor(
                name="context-schema",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="context-schema-plugin-factory",
                instance="context-schema",
                specification=SPEC_CONTEXT_SCHEMA,
                properties={"plugin.context_schema": context_schema},
            ),
            PluginDescriptor(
                name="checkpointer",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="checkpointer-plugin-factory",
                instance="checkpointer",
                specification=SPEC_CHECKPOINTER,
                properties={"plugin.checkpointer": checkpointer},
            ),
            PluginDescriptor(
                name="store",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="store-plugin-factory",
                instance="store",
                specification=SPEC_STORE,
                properties={"plugin.store": store},
            ),
            PluginDescriptor(
                name="interrupt-before",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="interrupt-before-plugin-factory",
                instance="interrupt-before",
                specification=SPEC_INTERRUPT_BEFORE,
                properties={"plugin.interrupt_before": ["before_a", "before_b"]},
            ),
            PluginDescriptor(
                name="interrupt-after",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="interrupt-after-plugin-factory",
                instance="interrupt-after",
                specification=SPEC_INTERRUPT_AFTER,
                properties={"plugin.interrupt_after": ["after_a"]},
            ),
            PluginDescriptor(
                name="debug",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="debug-plugin-factory",
                instance="debug",
                specification=SPEC_DEBUG,
                properties={"plugin.debug": True},
            ),
            PluginDescriptor(
                name="agent-name",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="agent-name-plugin-factory",
                instance="agent-name",
                specification=SPEC_NAME,
                properties={"plugin.agent_name": "my-agent"},
            ),
            PluginDescriptor(
                name="cache",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="cache-plugin-factory",
                instance="cache",
                specification=SPEC_CACHE,
                properties={"plugin.cache": cache},
            ),
            PluginDescriptor(
                name="transformers",
                version="1.0.0",
                module="langharmess.plugins.agent_params",
                factory="transformers-plugin-factory",
                instance="transformers",
                specification=SPEC_TRANSFORMERS,
                properties={"plugin.transformers": ["transformer_a"]},
            ),
        ]

        for descriptor in parameter_descriptors:
            manager.install_plugin(descriptor)

        loop._rebuild()

        assert captured_kwargs["response_format"] is response_format
        assert captured_kwargs["state_schema"] is state_schema
        assert captured_kwargs["context_schema"] is context_schema
        assert captured_kwargs["checkpointer"] is checkpointer
        assert captured_kwargs["store"] is store
        assert captured_kwargs["interrupt_before"] == ["before_a", "before_b"]
        assert captured_kwargs["interrupt_after"] == ["after_a"]
        assert captured_kwargs["debug"] is True
        assert captured_kwargs["name"] == "my-agent"
        assert captured_kwargs["cache"] is cache
        assert captured_kwargs["transformers"] == ["transformer_a"]
    finally:
        manager.stop()
