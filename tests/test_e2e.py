"""End-to-end tests that start the real Pelix/iPOPO framework."""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from langharmess.contracts import SPEC_AGENT_LOOP, SPEC_SYSTEM_PROMPT
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


def test_plugin_lifecycle_and_agent_invocation(tmp_path: Path) -> None:
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
    finally:
        manager.stop()
