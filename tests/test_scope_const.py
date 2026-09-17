"""Canonical scope constants live in one module."""

from __future__ import annotations

from langharmess_plugin.scope_const import (
    AGENT_SCOPE_ID,
    BUILTIN_SCOPES,
    PLUGIN_KEY,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_SCOPE_ID,
    ROOT_SCOPE_ID,
    SERVER_SCOPE_ID,
    UI_SCOPE_ID,
    agent_instance_scope_id,
)
from langharmess_scope import ScopeId


def test_builtin_scope_ids_are_canonical() -> None:
    assert UI_SCOPE_ID == ScopeId("ui")
    assert SERVER_SCOPE_ID == ScopeId("server")
    assert AGENT_SCOPE_ID == ScopeId("agent")
    assert ROOT_SCOPE_ID == ScopeId("root")


def test_agent_instance_scope_id_uses_colon_format() -> None:
    assert agent_instance_scope_id("a") == ScopeId("agent:a")


def test_builtin_scopes_declare_the_fixed_topology() -> None:
    assert BUILTIN_SCOPES == (
        (UI_SCOPE_ID, "UI", ROOT_SCOPE_ID),
        (SERVER_SCOPE_ID, "Server", ROOT_SCOPE_ID),
        (AGENT_SCOPE_ID, "Agent", ROOT_SCOPE_ID),
    )


def test_plugin_metadata_keys_are_exported() -> None:
    assert PLUGIN_SCOPE_ID == "plugin.scope_id"
    assert PLUGIN_SCOPE_CHAIN == "plugin.scope_chain"
    assert PLUGIN_KEY == "plugin.key"
