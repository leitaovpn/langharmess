"""Demo components consume the real core service contracts."""

from __future__ import annotations

from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_TOOL,
    AgentLoopProvider,
    LLMProvider,
    MiddlewareProvider,
    ToolProvider,
)

__all__ = [
    "SPEC_AGENT_LOOP",
    "SPEC_LLM",
    "SPEC_MIDDLEWARE",
    "SPEC_TOOL",
    "AgentLoopProvider",
    "LLMProvider",
    "MiddlewareProvider",
    "ToolProvider",
]
