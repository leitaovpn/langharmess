"""Tool plugin: contributes the ``add`` tool to the agent loop."""

from __future__ import annotations

from langchain_core.tools import tool
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Property,
    Provides,
)

from plugin_demo.contracts import SPEC_TOOL


@tool
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


@ComponentFactory("calculator-tool-factory")
@Instantiate("calculator-tool")
@Provides(SPEC_TOOL)
@Property("_plugin_name", "plugin.name", "calculator-tool")
@Property("_plugin_version", "plugin.version", "1.0.0")
class CalculatorToolPlugin:
    """Exposes one or more LangChain tools."""

    def get_tools(self):
        return [add]

    def get_plugin_info(self):
        return {"name": self._plugin_name, "version": self._plugin_version}
