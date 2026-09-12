"""LLM plugin."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides

from langharmess.contracts import SPEC_LLM


@ComponentFactory("llm-plugin-factory")
@Provides(SPEC_LLM)
@Property("_plugin_name", "plugin.name", "llm-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_ranking", "service.ranking", 100)
@Property("_model_name", "plugin.model.name", "")
@HiddenProperty("_model_instance", "plugin.model.instance", None)
class LLMPlugin:
    """Provides a LangChain chat model to the agent loop."""

    def __init__(self) -> None:
        self._plugin_name = "llm-plugin"
        self._plugin_version = "1.0.0"
        self._ranking = 100
        self._model_name = ""
        self._model_instance: Any = None

    def get_model(self) -> Any:
        if self._model_instance is not None:
            return self._model_instance
        if self._model_name:
            return init_chat_model(self._model_name)
        return ChatOpenAI(model="gpt-4o-mini")

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
