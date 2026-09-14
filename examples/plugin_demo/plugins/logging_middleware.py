"""Middleware plugin: contributes an AgentMiddleware to the agent loop."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import before_model
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Property,
    Provides,
)

from plugin_demo.contracts import MiddlewareProvider


@before_model
def log_before_model(state, runtime):
    """Log the number of messages right before each model call."""
    print(f"[middleware:logging] before_model, messages={len(state['messages'])}")
    return None


@ComponentFactory("logging-middleware-factory")
@Instantiate("logging-middleware")
@Provides(MiddlewareProvider)
@Property("_plugin_name", "plugin.name", "logging-middleware")
@Property("_plugin_version", "plugin.version", "1.0.0")
class LoggingMiddlewarePlugin:
    """Exposes one or more LangChain AgentMiddleware instances."""

    def get_middlewares(self) -> list[Any]:
        return [log_before_model]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
