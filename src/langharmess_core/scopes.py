"""Canonical scope identifiers for the built-in runtime topology."""

from langharmess_scope import ROOT_SCOPE_ID, ScopeId

UI_SCOPE_ID = ScopeId("ui")
SERVER_SCOPE_ID = ScopeId("server")
AGENT_SCOPE_ID = ScopeId("agent")


def agent_instance_scope_id(agent_id: str) -> ScopeId:
    return ScopeId(f"agent/{agent_id}")


__all__ = [
    "AGENT_SCOPE_ID",
    "ROOT_SCOPE_ID",
    "SERVER_SCOPE_ID",
    "UI_SCOPE_ID",
    "agent_instance_scope_id",
]
