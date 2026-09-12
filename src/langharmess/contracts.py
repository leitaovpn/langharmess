"""Public service specifications shared by all plugins."""

from __future__ import annotations

SPEC_LLM = "agent.plugin.llm"
SPEC_TOOL = "agent.plugin.tools"
SPEC_MIDDLEWARE = "agent.plugin.middleware"
SPEC_AGENT_LOOP = "agent.loop"

ALL_PLUGIN_SPECS = (SPEC_LLM, SPEC_TOOL, SPEC_MIDDLEWARE, SPEC_AGENT_LOOP)
