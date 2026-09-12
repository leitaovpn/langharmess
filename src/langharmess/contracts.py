"""Public service specifications shared by all plugins."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel

SPEC_LLM = "agent.plugin.llm"
SPEC_TOOL = "agent.plugin.tools"
SPEC_MIDDLEWARE = "agent.plugin.middleware"
SPEC_SYSTEM_PROMPT = "agent.plugin.system_prompt"
SPEC_AGENT_LOOP = "agent.loop"

ALL_PLUGIN_SPECS = (
    SPEC_LLM,
    SPEC_TOOL,
    SPEC_MIDDLEWARE,
    SPEC_SYSTEM_PROMPT,
    SPEC_AGENT_LOOP,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Contract implemented by every ``agent.plugin.llm`` service."""

    def get_model(self) -> BaseChatModel: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class ToolProvider(Protocol):
    """Contract implemented by every ``agent.plugin.tools`` service."""

    def get_tools(self) -> list[Any]: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class MiddlewareProvider(Protocol):
    """Contract implemented by every ``agent.plugin.middleware`` service."""

    def get_middlewares(self) -> list[Any]: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class SystemPromptProvider(Protocol):
    """Contract implemented by every ``agent.plugin.system_prompt`` service."""

    def get_system_prompt(self) -> str: ...

    def get_plugin_info(self) -> dict[str, str]: ...
