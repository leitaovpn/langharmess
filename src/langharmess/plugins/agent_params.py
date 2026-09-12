"""Plugins for the remaining ``create_agent`` parameters."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import (
    ComponentFactory,
    HiddenProperty,
    Property,
    Provides,
)

from langharmess.contracts import (
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
    SPEC_TRANSFORMERS,
)


@ComponentFactory("response-format-plugin-factory")
@Provides(SPEC_RESPONSE_FORMAT)
@Property("_plugin_name", "plugin.name", "response-format-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_response_format", "plugin.response_format", None)
class ResponseFormatPlugin:
    def __init__(self) -> None:
        self._plugin_name = "response-format-plugin"
        self._plugin_version = "1.0.0"
        self._response_format: Any = None

    def get_response_format(self) -> Any:
        return self._response_format


@ComponentFactory("state-schema-plugin-factory")
@Provides(SPEC_STATE_SCHEMA)
@Property("_plugin_name", "plugin.name", "state-schema-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_state_schema", "plugin.state_schema", None)
class StateSchemaPlugin:
    def __init__(self) -> None:
        self._plugin_name = "state-schema-plugin"
        self._plugin_version = "1.0.0"
        self._state_schema: Any = None

    def get_state_schema(self) -> Any:
        return self._state_schema


@ComponentFactory("context-schema-plugin-factory")
@Provides(SPEC_CONTEXT_SCHEMA)
@Property("_plugin_name", "plugin.name", "context-schema-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_context_schema", "plugin.context_schema", None)
class ContextSchemaPlugin:
    def __init__(self) -> None:
        self._plugin_name = "context-schema-plugin"
        self._plugin_version = "1.0.0"
        self._context_schema: Any = None

    def get_context_schema(self) -> Any:
        return self._context_schema


@ComponentFactory("checkpointer-plugin-factory")
@Provides(SPEC_CHECKPOINTER)
@Property("_plugin_name", "plugin.name", "checkpointer-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_checkpointer", "plugin.checkpointer", None)
class CheckpointerPlugin:
    def __init__(self) -> None:
        self._plugin_name = "checkpointer-plugin"
        self._plugin_version = "1.0.0"
        self._checkpointer: Any = None

    def get_checkpointer(self) -> Any:
        return self._checkpointer


@ComponentFactory("store-plugin-factory")
@Provides(SPEC_STORE)
@Property("_plugin_name", "plugin.name", "store-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_store", "plugin.store", None)
class StorePlugin:
    def __init__(self) -> None:
        self._plugin_name = "store-plugin"
        self._plugin_version = "1.0.0"
        self._store: Any = None

    def get_store(self) -> Any:
        return self._store


@ComponentFactory("interrupt-before-plugin-factory")
@Provides(SPEC_INTERRUPT_BEFORE)
@Property("_plugin_name", "plugin.name", "interrupt-before-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.interrupt_before", None)
class InterruptBeforePlugin:
    def __init__(self) -> None:
        self._plugin_name = "interrupt-before-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_interrupt_before(self) -> list[str]:
        return list(self._items or [])


@ComponentFactory("interrupt-after-plugin-factory")
@Provides(SPEC_INTERRUPT_AFTER)
@Property("_plugin_name", "plugin.name", "interrupt-after-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.interrupt_after", None)
class InterruptAfterPlugin:
    def __init__(self) -> None:
        self._plugin_name = "interrupt-after-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_interrupt_after(self) -> list[str]:
        return list(self._items or [])


@ComponentFactory("debug-plugin-factory")
@Provides(SPEC_DEBUG)
@Property("_plugin_name", "plugin.name", "debug-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_debug", "plugin.debug", False)
class DebugPlugin:
    def __init__(self) -> None:
        self._plugin_name = "debug-plugin"
        self._plugin_version = "1.0.0"
        self._debug = False

    def get_debug(self) -> bool:
        return self._debug


@ComponentFactory("agent-name-plugin-factory")
@Provides(SPEC_NAME)
@Property("_plugin_name", "plugin.name", "agent-name-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_agent_name", "plugin.agent_name", "")
class AgentNamePlugin:
    def __init__(self) -> None:
        self._plugin_name = "agent-name-plugin"
        self._plugin_version = "1.0.0"
        self._agent_name = ""

    def get_name(self) -> str | None:
        return self._agent_name or None


@ComponentFactory("cache-plugin-factory")
@Provides(SPEC_CACHE)
@Property("_plugin_name", "plugin.name", "cache-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@HiddenProperty("_cache", "plugin.cache", None)
class CachePlugin:
    def __init__(self) -> None:
        self._plugin_name = "cache-plugin"
        self._plugin_version = "1.0.0"
        self._cache: Any = None

    def get_cache(self) -> Any:
        return self._cache


@ComponentFactory("transformers-plugin-factory")
@Provides(SPEC_TRANSFORMERS)
@Property("_plugin_name", "plugin.name", "transformers-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_items", "plugin.transformers", None)
class TransformersPlugin:
    def __init__(self) -> None:
        self._plugin_name = "transformers-plugin"
        self._plugin_version = "1.0.0"
        self._items: Any = None

    def get_transformers(self) -> list[Any]:
        return list(self._items or [])
