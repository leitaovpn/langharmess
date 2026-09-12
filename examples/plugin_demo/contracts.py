"""Plugin service specification names.

Keeping these as plain strings mirrors Pelix/iPOPO's service-oriented style:
components are decoupled by specification, not by importing each other's
concrete classes.
"""

from __future__ import annotations

SPEC_LLM = "agent.plugin.llm"
SPEC_TOOL = "agent.plugin.tools"
SPEC_MIDDLEWARE = "agent.plugin.middleware"
SPEC_AGENT_LOOP = "agent.loop"
