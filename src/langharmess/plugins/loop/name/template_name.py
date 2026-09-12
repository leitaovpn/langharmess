"""Agent name plugin."""

from __future__ import annotations

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess.contracts import SPEC_NAME


@ComponentFactory("agent-name-plugin-factory")
@Provides(SPEC_NAME)
@Property("_plugin_name", "plugin.name", "agent-name-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_agent_name", "plugin.agent_name", "")
class TemplateAgentNamePlugin:
    def __init__(self) -> None:
        self._plugin_name = "agent-name-plugin"
        self._plugin_version = "1.0.0"
        self._agent_name = ""

    def get_name(self) -> str | None:
        return self._agent_name or None
