"""Tests for the interactive session and agent commands."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from langharmess_cli.plugins.commands.session import SessionCommandPlugin

AGENTS = [
    {
        "id": "simple_agent",
        "name": "Simple Agent",
        "description": "Built-in agent.",
        "enabled": True,
    },
    {
        "id": "researcher",
        "name": "Researcher",
        "description": "Reads a lot.",
        "enabled": True,
    },
    {
        "id": "retired",
        "name": "Retired",
        "description": "Disabled agent.",
        "enabled": False,
    },
]

SESSIONS = [
    {
        "session_id": "current-session",
        "turns": 4,
        "last_agent_id": "simple_agent",
        "last_used_at": "2026-09-15T10:00:00+00:00",
    },
    {
        "session_id": "older-session",
        "turns": 1,
        "last_agent_id": "researcher",
        "last_used_at": "2026-09-14T10:00:00+00:00",
    },
]


class Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://api/agents")
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(self.status_code)
            )


class Context:
    def __init__(self) -> None:
        self.base_url = "http://api"
        self.token = "secret"
        self.user_id = "local_user"
        self.agent_id = "simple_agent"
        self.session_id: str | None = "current-session"
        self.refreshes = 0

    def refresh_status(self) -> None:
        self.refreshes += 1

    def list_providers(self) -> list[str]:
        return []

    def switch_provider(self, name: str) -> bool:
        return True


def make_plugin(locale: str = "en") -> SessionCommandPlugin:
    plugin = SessionCommandPlugin()
    plugin._locale = locale
    return plugin


def handler_for(plugin: SessionCommandPlugin, name: str) -> Any:
    commands = {command.name: command for command in plugin.get_interactive_commands()}
    return commands[name].handler


def test_plugin_exposes_session_commands() -> None:
    plugin = make_plugin()
    assert [command.name for command in plugin.get_interactive_commands()] == [
        "agents",
        "agent",
        "sessions",
        "new",
        "whoami",
    ]
    assert plugin.get_commands() == []
    assert plugin.get_plugin_info() == {"name": "session-command", "version": "1.0.0"}


def test_agents_command_lists_agents_and_marks_current(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    plugin = make_plugin()
    context = Context()

    assert handler_for(plugin, "agents")(context, "") is False

    output = capsys.readouterr().out
    assert "Available agents:" in output
    assert "* simple_agent" in output
    assert "  researcher" in output
    assert "disabled" in output


def test_agents_command_reports_empty_registry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": []})
    )
    assert handler_for(make_plugin(), "agents")(Context(), "") is False
    assert "No agents are registered" in capsys.readouterr().out


def test_agents_command_reports_request_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fail)
    assert handler_for(make_plugin(), "agents")(Context(), "") is False
    assert "Identity request failed" in capsys.readouterr().out


def test_agent_command_without_argument_shows_current_and_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    assert handler_for(make_plugin(), "agent")(Context(), "") is False
    output = capsys.readouterr().out
    assert "Current agent: simple_agent" in output
    assert "researcher" in output


def test_agent_command_switches_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    context = Context()
    assert handler_for(make_plugin(), "agent")(context, "researcher") is False
    assert context.agent_id == "researcher"
    assert context.refreshes == 1
    assert "Switched to agent researcher" in capsys.readouterr().out


def test_agent_command_keeps_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    context = Context()
    handler_for(make_plugin(), "agent")(context, "researcher")
    assert context.session_id == "current-session"


def test_agent_command_skips_lookup_for_current_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Response:
        raise AssertionError("should not call the API")

    monkeypatch.setattr(httpx, "get", fail)
    context = Context()
    assert handler_for(make_plugin(), "agent")(context, "simple_agent") is False
    assert "Current agent: simple_agent" in capsys.readouterr().out


def test_agent_command_rejects_unknown_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    context = Context()
    assert handler_for(make_plugin(), "agent")(context, "missing") is False
    assert context.agent_id == "simple_agent"
    assert "Unknown agent: missing" in capsys.readouterr().out


def test_agent_command_rejects_disabled_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"agents": AGENTS})
    )
    context = Context()
    assert handler_for(make_plugin(), "agent")(context, "retired") is False
    assert context.agent_id == "simple_agent"
    assert "Unknown agent: retired" in capsys.readouterr().out


def test_sessions_command_lists_sessions_per_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response({"user_id": "local_user", "sessions": SESSIONS})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert handler_for(make_plugin(), "sessions")(Context(), "") is False

    output = capsys.readouterr().out
    assert "Recent sessions for local_user:" in output
    assert "* current-session" in output
    assert "  older-session" in output
    assert captured["url"] == "http://api/sessions"
    assert captured["params"]["user_id"] == "local_user"


def test_sessions_command_reports_empty_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"sessions": []})
    )
    assert handler_for(make_plugin(), "sessions")(Context(), "") is False
    assert "No sessions found for local_user" in capsys.readouterr().out


def test_new_command_resets_session(
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = Context()
    assert handler_for(make_plugin(), "new")(context, "") is False
    assert context.session_id is None
    assert context.refreshes == 1
    assert "Next message starts a new session" in capsys.readouterr().out


def test_whoami_command_prints_identity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for(make_plugin(), "whoami")(Context(), "") is False
    output = capsys.readouterr().out
    assert "user local_user" in output
    assert "agent simple_agent" in output
    assert "session current-session" in output


def test_whoami_reports_pending_session(capsys: pytest.CaptureFixture[str]) -> None:
    context = Context()
    context.session_id = None
    handler_for(make_plugin(), "whoami")(context, "")
    assert "session new session" in capsys.readouterr().out


def test_commands_localize_in_chinese(capsys: pytest.CaptureFixture[str]) -> None:
    plugin = make_plugin(locale="zh")
    context = Context()
    handler_for(plugin, "new")(context, "")
    assert "下一条消息将开始新会话" in capsys.readouterr().out
    handler_for(plugin, "whoami")(context, "")
    assert "agent simple_agent" in capsys.readouterr().out
