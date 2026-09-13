"""LLM plugin implementation."""

from __future__ import annotations

from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Property, Provides
from pydantic import SecretStr

from langharmess_core.contracts import SPEC_LLM, ModelProtocol


@ComponentFactory("llm-plugin-factory")
@Provides(SPEC_LLM)
@Property("_plugin_name", "plugin.name", "llm-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_ranking", "service.ranking", 100)
@Property("_model_name", "plugin.model.name", "")
@HiddenProperty("_api_key", "plugin.model.api_key", "")
@Property("_base_url", "plugin.model.base_url", "")
@Property("_protocol", "plugin.model.protocol", "chat")
@Property("_stream_usage", "plugin.model.stream_usage", True)
@HiddenProperty("_model_instance", "plugin.model.instance", None)
class LLMPlugin:
    """Provides a LangChain chat model to the agent loop."""

    def __init__(self) -> None:
        self._plugin_name = "llm-plugin"
        self._plugin_version = "1.0.0"
        self._ranking = 100
        self._model_name = ""
        self._api_key = ""
        self._base_url = ""
        self._protocol = "chat"
        self._stream_usage = True
        self._model_instance: Any = None

    def get_model(self) -> Any:
        if self._model_instance is not None:
            return self._model_instance
        if self._protocol == "anthropic":
            anthropic_options: dict[str, Any] = {
                "model_name": self._model_name,
                "api_key": SecretStr(self._api_key) if self._api_key else None,
                "base_url": self._base_url or None,
            }
            return ChatAnthropic(**anthropic_options)
        if self._protocol not in {"chat", "responses"}:
            raise ValueError(f"Unsupported LLM protocol: {self._protocol}")
        if self._model_name:
            if self._protocol == "responses" or self._api_key or self._base_url:
                return ChatOpenAI(
                    model=self._model_name,
                    api_key=SecretStr(self._api_key) if self._api_key else None,
                    base_url=self._base_url or None,
                    stream_usage=self._stream_usage,
                    use_responses_api=self._protocol == "responses",
                )
            model = init_chat_model(self._model_name)
            if hasattr(model, "stream_usage"):
                setattr(model, "stream_usage", self._stream_usage)
            return model
        return ChatOpenAI(
            model="gpt-4o-mini",
            stream_usage=self._stream_usage,
            use_responses_api=self._protocol == "responses",
        )

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def get_protocol(self) -> ModelProtocol:
        if self._protocol not in {"anthropic", "chat", "responses"}:
            raise ValueError(f"Unsupported LLM protocol: {self._protocol}")
        return cast(ModelProtocol, self._protocol)
