"""System prompt plugin."""

from __future__ import annotations

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_core.contracts import SPEC_SYSTEM_PROMPT


@ComponentFactory("system-prompt-plugin-factory")
@Provides(SPEC_SYSTEM_PROMPT)
@Property("_plugin_name", "plugin.name", "system-prompt-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_system_prompt", "plugin.system_prompt", "")
class TemplateSystemPromptPlugin:
    """Provides one piece of the agent system prompt."""

    def __init__(self) -> None:
        self._plugin_name = "system-prompt-plugin"
        self._plugin_version = "1.0.0"
        self._system_prompt = ""

    def get_system_prompt(self) -> str:
        return self._system_prompt

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
