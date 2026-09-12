"""Middleware plugin."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import before_model
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess.contracts import SPEC_MIDDLEWARE


@ComponentFactory("middleware-plugin-factory")
@Provides(SPEC_MIDDLEWARE)
@Property("_plugin_name", "plugin.name", "middleware-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
class TemplateMiddlewarePlugin:
    """Provides LangChain middleware to the agent loop."""

    def __init__(self) -> None:
        self._plugin_name = "middleware-plugin"
        self._plugin_version = "1.0.0"

    def get_middlewares(self) -> list[Any]:
        @before_model(name=self._plugin_name)
        def hook(state: Any, runtime: Any) -> None:
            print(f"[middleware:{self._plugin_name}] messages={len(state['messages'])}")
            return None

        return [hook]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
