"""Human approval middleware for dangerous LangChain tool calls."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import HumanInTheLoopMiddleware
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_core.contracts import MiddlewareProvider


@ComponentFactory("human-approval-plugin-factory")
@Provides(MiddlewareProvider)
@Property("_plugin_name", "plugin.name", "human-approval-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_dangerous_tools", "plugin.approval.tools", None)
class HumanApprovalPlugin:
    """Adds LangChain's interrupt-based human approval gate.

    ``plugin.approval.tools`` is a list of tool names requiring review.  The
    graph pauses before execution and resumes after a LangGraph decision.
    """

    def __init__(self) -> None:
        self._plugin_name = "human-approval-plugin"
        self._plugin_version = "1.0.0"
        self._dangerous_tools: Any = None

    def get_middlewares(self) -> list[Any]:
        names = self._dangerous_tools or []
        if isinstance(names, str):
            names = [item.strip() for item in names.split(",") if item.strip()]
        interrupt_on: dict[str, Any] = {str(name): True for name in names}
        if not interrupt_on:
            return []
        return [HumanInTheLoopMiddleware(interrupt_on)]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
