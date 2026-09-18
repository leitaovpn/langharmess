"""Regression tests for aggregate dependency unbind ordering."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import langharness_core.plugins.loop.agent_loop as agent_loop_module
from langharness_core.plugins.loop.agent_loop import PluginAgentLoop


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name

    def get_tools(self) -> list[Any]:
        return [self]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self.name, "version": "1.0.0"}


def test_tool_unbind_rebuild_excludes_removed_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = FakeTool("old-tool")
    new = FakeTool("new-tool")
    loop = PluginAgentLoop()
    loop._tool_providers = [old, new]
    loop._llm_provider = SimpleNamespace(
        get_model=lambda: object(),
        get_plugin_info=lambda: {"name": "fake-llm", "version": "1.0.0"},
    )
    captured: dict[str, Any] = {}

    def fake_create_agent(model: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_loop_module, "create_agent", fake_create_agent)

    loop._on_tool_unbind("_tool_providers", old, None)

    assert [tool.name for tool in captured["tools"]] == ["new-tool"]
    assert loop._excluded_services == set()
