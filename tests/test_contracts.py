"""Contract tests for plugin service specifications and protocols."""

from __future__ import annotations

from typing import Any

import pytest

from langharmess_core import contracts
from langharmess_core.plugins.agents.registry import AgentRegistryPlugin
from langharmess_core.plugins.llm.llm import LLMPlugin
from langharmess_core.plugins.middleware.template_middleware import (
    TemplateMiddlewarePlugin,
)
from langharmess_core.plugins.sessions.sqlite import SQLiteSessionIndexPlugin
from langharmess_core.plugins.system_prompt.template_system_prompt import (
    TemplateSystemPromptPlugin,
)
from langharmess_core.plugins.tools.tools import ToolPlugin
from langharmess_plugin.validation import contract_for, validate

PROTOCOLS = (
    (contracts.SPEC_LLM, contracts.LLMProvider, LLMPlugin),
    (contracts.SPEC_TOOL, contracts.ToolProvider, ToolPlugin),
    (
        contracts.SPEC_MIDDLEWARE,
        contracts.MiddlewareProvider,
        TemplateMiddlewarePlugin,
    ),
    (
        contracts.SPEC_SYSTEM_PROMPT,
        contracts.SystemPromptProvider,
        TemplateSystemPromptPlugin,
    ),
    (
        contracts.SPEC_SESSION_INDEX,
        contracts.SessionIndexProvider,
        SQLiteSessionIndexPlugin,
    ),
    (
        contracts.SPEC_AGENT_REGISTRY,
        contracts.AgentRegistryProvider,
        AgentRegistryPlugin,
    ),
)


@pytest.mark.parametrize(("specification", "protocol", "plugin"), PROTOCOLS)
def test_protocols_are_pinned_to_their_specifications(
    specification: str, protocol: type[Any], plugin: type[Any]
) -> None:
    assert contract_for(specification) is protocol
    assert isinstance(plugin(), protocol)


@pytest.mark.parametrize(
    ("protocol", "plugin"),
    [(protocol, plugin) for _, protocol, plugin in PROTOCOLS],
)
def test_concrete_plugins_conform_to_their_protocols(
    protocol: type[Any], plugin: type[Any]
) -> None:
    assert validate(plugin(), protocol) == ()


def test_pin_does_not_pollute_protocol_members() -> None:
    for _, protocol, _ in PROTOCOLS:
        assert "__SPECIFICATION__" not in getattr(protocol, "__protocol_attrs__")


def test_agent_loop_contract_is_pinned() -> None:
    from langharmess_core.plugins.loop.agent_loop import PluginAgentLoop

    assert contract_for(contracts.SPEC_AGENT_LOOP) is contracts.AgentLoopProvider
    assert validate(PluginAgentLoop(), contracts.AgentLoopProvider) == ()
