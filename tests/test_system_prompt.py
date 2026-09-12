"""Tests for the system-prompt plugin vertical slice."""
# mypy: ignore-errors

from __future__ import annotations

from types import SimpleNamespace

import pytest

import langharmess.agent_loop as agent_loop_module
from langharmess.agent_loop import PluginAgentLoop
from langharmess.plugins.loop.system_prompt.template_system_prompt import (
    TemplateSystemPromptPlugin,
)


def make_provider(text: str):
    return SimpleNamespace(get_system_prompt=lambda: text)


def test_system_prompt_plugin_exposes_configured_prompt() -> None:
    plugin = TemplateSystemPromptPlugin()
    plugin._system_prompt = "You are a calculator."
    assert plugin.get_system_prompt() == "You are a calculator."
    assert plugin.get_plugin_info() == {
        "name": "system-prompt-plugin",
        "version": "1.0.0",
    }


def test_collect_system_prompt_joins_multiple_providers() -> None:
    loop = PluginAgentLoop()
    loop._system_prompt_providers = [
        make_provider("You are A."),
        make_provider("You are B."),
    ]
    assert loop._collect_system_prompt() == "You are A.\nYou are B."


def test_collect_system_prompt_returns_none_when_empty() -> None:
    loop = PluginAgentLoop()
    loop._system_prompt_providers = []
    assert loop._collect_system_prompt() is None


def test_rebuild_passes_system_prompt_to_create_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_agent(model, tools=None, *, system_prompt=None, **kwargs):
        captured["model"] = model
        captured["system_prompt"] = system_prompt
        return object()

    monkeypatch.setattr(agent_loop_module, "create_agent", fake_create_agent)

    loop = PluginAgentLoop()
    loop._llm_provider = SimpleNamespace(get_model=lambda: object())
    loop._tool_providers = []
    loop._middleware_providers = []
    loop._system_prompt_providers = [
        make_provider("You are A."),
        make_provider("You are B."),
    ]

    loop._rebuild()

    assert captured["system_prompt"] == "You are A.\nYou are B."
