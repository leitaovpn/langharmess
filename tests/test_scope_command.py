"""Tests for the scope tree command plugin."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from langharmess_cli.plugins.commands.scope import ScopeCommandPlugin

SCOPE_PAYLOAD = {
    "scopes": [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "ui", "parent_id": "root", "name": "UI"},
        {"id": "server", "parent_id": "root", "name": "Server"},
        {"id": "agent", "parent_id": "root", "name": "Agent"},
        {"id": "agent:a", "parent_id": "agent", "name": "A"},
    ]
}


class Context:
    def __init__(self) -> None:
        self.base_url = "http://api"
        self.token = "secret"

    def refresh_status(self) -> None:
        return None


class Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://api/scope")
            raise httpx.HTTPStatusError(
                str(self._payload),
                request=request,
                response=httpx.Response(self.status_code, json=self._payload),
            )


def make_plugin() -> ScopeCommandPlugin:
    return ScopeCommandPlugin()


def test_scope_exposes_command_specs() -> None:
    plugin = make_plugin()
    assert [item.name for item in plugin.get_commands()] == ["scope"]
    assert [item.name for item in plugin.get_interactive_commands()] == ["scope"]
    assert plugin.get_plugin_info() == {"name": "scope-command", "version": "1.0.0"}


def test_scope_renders_indented_tree(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(SCOPE_PAYLOAD))
    command = {item.name: item for item in plugin.get_interactive_commands()}["scope"]

    assert command.handler(Context(), "") is False

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "root",
        "├── agent",
        "│   └── agent:a",
        "├── server",
        "└── ui",
    ]


def test_scope_prints_json_for_noninteractive_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(SCOPE_PAYLOAD))
    command = plugin.get_commands()[0]

    assert command.handler(type("Args", (), {})()) == 0
    assert '"scopes"' in capsys.readouterr().out


def test_scope_reports_request_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin = make_plugin()
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"detail": "boom"}, status_code=503)
    )
    command = {item.name: item for item in plugin.get_interactive_commands()}["scope"]

    assert command.handler(Context(), "") is False
    assert "Scope request failed" in capsys.readouterr().out
