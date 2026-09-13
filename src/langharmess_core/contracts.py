"""Public service specifications shared by all plugins."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel

SPEC_LLM = "agent.plugin.llm"
SPEC_TOOL = "agent.plugin.tools"
SPEC_MIDDLEWARE = "agent.plugin.middleware"
SPEC_SYSTEM_PROMPT = "agent.plugin.system_prompt"
SPEC_RESPONSE_FORMAT = "agent.plugin.response_format"
SPEC_STATE_SCHEMA = "agent.plugin.state_schema"
SPEC_CONTEXT_SCHEMA = "agent.plugin.context_schema"
SPEC_CHECKPOINTER = "agent.plugin.checkpointer"
SPEC_STORE = "agent.plugin.store"
SPEC_INTERRUPT_BEFORE = "agent.plugin.interrupt_before"
SPEC_INTERRUPT_AFTER = "agent.plugin.interrupt_after"
SPEC_DEBUG = "agent.plugin.debug"
SPEC_NAME = "agent.plugin.name"
SPEC_CACHE = "agent.plugin.cache"
SPEC_TRANSFORMERS = "agent.plugin.transformers"
SPEC_AGENT_LOOP = "agent.loop"
ModelProtocol = Literal["anthropic", "chat", "responses"]

ALL_PLUGIN_SPECS = (
    SPEC_LLM,
    SPEC_TOOL,
    SPEC_MIDDLEWARE,
    SPEC_SYSTEM_PROMPT,
    SPEC_RESPONSE_FORMAT,
    SPEC_STATE_SCHEMA,
    SPEC_CONTEXT_SCHEMA,
    SPEC_CHECKPOINTER,
    SPEC_STORE,
    SPEC_INTERRUPT_BEFORE,
    SPEC_INTERRUPT_AFTER,
    SPEC_DEBUG,
    SPEC_NAME,
    SPEC_CACHE,
    SPEC_TRANSFORMERS,
    SPEC_AGENT_LOOP,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Contract implemented by every ``agent.plugin.llm`` service."""

    def get_model(self) -> BaseChatModel: ...

    def get_protocol(self) -> ModelProtocol: ...

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


@runtime_checkable
class ResponseFormatProvider(Protocol):
    def get_response_format(self) -> Any: ...


@runtime_checkable
class StateSchemaProvider(Protocol):
    def get_state_schema(self) -> Any: ...


@runtime_checkable
class ContextSchemaProvider(Protocol):
    def get_context_schema(self) -> Any: ...


@runtime_checkable
class CheckpointerProvider(Protocol):
    def get_checkpointer(self) -> Any: ...


@runtime_checkable
class StoreProvider(Protocol):
    def get_store(self) -> Any: ...


@runtime_checkable
class InterruptBeforeProvider(Protocol):
    def get_interrupt_before(self) -> list[str]: ...


@runtime_checkable
class InterruptAfterProvider(Protocol):
    def get_interrupt_after(self) -> list[str]: ...


@runtime_checkable
class DebugProvider(Protocol):
    def get_debug(self) -> bool: ...


@runtime_checkable
class NameProvider(Protocol):
    def get_name(self) -> str | None: ...


@runtime_checkable
class CacheProvider(Protocol):
    def get_cache(self) -> Any: ...


@runtime_checkable
class TransformersProvider(Protocol):
    def get_transformers(self) -> list[Any]: ...
