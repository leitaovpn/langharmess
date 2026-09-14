"""LLM plugin: contributes a chat model to the agent loop."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Property,
    Provides,
)

from langharmess_core.contracts import ModelProtocol
from plugin_demo.contracts import LLMProvider
from plugin_demo.models import ScriptedToolCallModel


@ComponentFactory("fake-llm-factory")
@Instantiate("fake-llm")
@Provides(LLMProvider)
@Property("_plugin_name", "plugin.name", "fake-llm")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_ranking", "service.ranking", 100)
class FakeLLMPlugin:
    """Provides the model used by the plugin-driven agent."""

    def __init__(self):
        self._model = ScriptedToolCallModel(
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

    def get_model(self) -> BaseChatModel:
        return self._model

    def get_protocol(self) -> ModelProtocol:
        return "chat"

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
