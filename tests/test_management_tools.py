"""Unit tests for the management tools plugin."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from langharmess_core.plugins.tools.management import ManagementToolsPlugin
from langharmess_scope import Scope, ScopeId

READ_TOOLS = {"list_scope_tree", "list_runtime_plugins", "discover_plugins"}


def _registration(name: str = "demo-plugin", scope_id: str = "agent") -> Any:
    return SimpleNamespace(
        package_id="dynamic.core",
        contribution_id="demo-template",
        package_version="1.0.0",
        scope_id=ScopeId(scope_id),
        enabled=True,
        status="installed",
        descriptor=SimpleNamespace(
            name=name,
            module="langharmess_core.plugins.tools.demo",
            specification="agent.plugin.tools",
        ),
    )


class FakeManager:
    def __init__(self) -> None:
        self.rescan_calls = 0
        self.registrations_ = [
            _registration(),
            _registration(name="other-plugin", scope_id="server"),
        ]
        self.scopes_ = (
            Scope(ScopeId("root"), None, "root"),
            Scope(ScopeId("agent"), ScopeId("root"), "agent"),
            Scope(ScopeId("agent:a"), ScopeId("agent"), "A"),
        )
        self.discovered_ = [
            SimpleNamespace(
                id="dynamic.core",
                version="1.0.0",
                contributions=[
                    SimpleNamespace(
                        id="demo-template",
                        descriptor=SimpleNamespace(
                            name="demo-template",
                            module="langharmess_core.plugins.tools.demo",
                            specification="agent.plugin.tools",
                        ),
                        target="agent",
                    )
                ],
            )
        ]

    def scopes(self) -> tuple[Scope, ...]:
        return self.scopes_

    def registrations(self) -> list[Any]:
        return self.registrations_

    def rescan(self) -> Any:
        self.rescan_calls += 1
        return SimpleNamespace(packages=(), failures=())

    def discovered(self) -> list[Any]:
        return self.discovered_


def _plugin(manager: FakeManager) -> ManagementToolsPlugin:
    plugin = ManagementToolsPlugin()
    plugin._dynamic_manager = manager
    return plugin


def _tools(plugin: ManagementToolsPlugin) -> dict[str, Any]:
    return {tool.name: tool for tool in plugin.get_tools()}


def test_get_tools_empty_without_manager() -> None:
    assert ManagementToolsPlugin().get_tools() == []


def test_get_tools_exposes_read_tools() -> None:
    assert set(_tools(_plugin(FakeManager()))) == READ_TOOLS


def test_list_scope_tree_renders_tree() -> None:
    tool = _tools(_plugin(FakeManager()))["list_scope_tree"]
    assert tool.invoke({}) == {
        "scope_tree": "root\n└── agent\n    └── agent:a"
    }


def test_list_runtime_plugins_aggregates_all_scopes() -> None:
    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    result = tool.invoke({})
    assert [item["name"] for item in result["plugins"]] == [
        "demo-plugin",
        "other-plugin",
    ]


def test_list_runtime_plugins_filters_by_scope() -> None:
    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    result = tool.invoke({"scope": "server"})
    assert [item["name"] for item in result["plugins"]] == ["other-plugin"]
    assert result["plugins"][0]["scope_id"] == "server"


def test_list_runtime_plugins_rejects_bare_agent_prefix() -> None:
    from pydantic import ValidationError

    tool = _tools(_plugin(FakeManager()))["list_runtime_plugins"]
    with pytest.raises(ValidationError):
        tool.invoke({"scope": "agent:"})


def test_discover_plugins_rescans_and_lists() -> None:
    manager = FakeManager()
    tool = _tools(_plugin(manager))["discover_plugins"]
    result = tool.invoke({})
    assert manager.rescan_calls == 1
    assert result["packages"][0]["package_id"] == "dynamic.core"
    assert result["packages"][0]["contributions"][0]["id"] == "demo-template"
