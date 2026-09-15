"""Tests for the interactive plugin configuration commands."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from langharmess_cli.plugins.commands.plugins import PluginCommandPlugin

SCOPE_CONFIG = {
    "scope": "api",
    "version": 3,
    "plugins": {
        "api-rate-limit": {"enabled": True, "properties": {"plugin.limit": 100}},
        "api-auth": {"enabled": True, "properties": {}},
    },
}

HISTORY = {
    "scope": "api",
    "version": 3,
    "history": [
        {"seq": 1, "action": "init", "actor": "system", "ts": "t1"},
        {"seq": 2, "action": "set", "actor": "cli", "ts": "t2"},
        {"seq": 3, "action": "rollback", "actor": "cli", "ts": "t3", "target_seq": 1},
    ],
}

APPLY_RESULT = {
    "scope": "api",
    "version": 4,
    "applied": ["api-rate-limit"],
    "restart_required": ["api-log"],
}


class Context:
    def __init__(self) -> None:
        self.base_url = "http://api"
        self.token = "secret"
        self.user_id = "local_user"
        self.agent_id = "simple_agent"
        self.session_id = "s1"

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
            request = httpx.Request("GET", "http://api/plugins")
            raise httpx.HTTPStatusError(
                str(self._payload),
                request=request,
                response=httpx.Response(self.status_code),
            )


def make_plugin() -> PluginCommandPlugin:
    plugin = PluginCommandPlugin()
    plugin._locale = "en"
    return plugin


def handler_for(name: str) -> Any:
    commands = {item.name: item for item in make_plugin().get_interactive_commands()}
    return commands[name].handler


def test_plugin_exposes_plugin_commands() -> None:
    plugin = make_plugin()
    assert [item.name for item in plugin.get_interactive_commands()] == ["plugins"]
    assert plugin.get_commands() == []
    assert plugin.get_plugin_info() == {"name": "plugin-command", "version": "1.0.0"}


def test_plugins_lists_scope_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response(SCOPE_CONFIG)

    monkeypatch.setattr(httpx, "get", fake_get)
    assert handler_for("plugins")(Context(), "list") is False

    output = capsys.readouterr().out
    assert "scope api" in output
    assert "version 3" in output
    assert "api-rate-limit" in output
    assert "plugin.limit=100" in output
    assert captured["params"] == {"scope": "api"}


def test_plugins_lists_agent_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> Response:
        captured.update(kwargs)
        return Response({"scope": "agent:alpha", "version": 1, "plugins": {}})

    monkeypatch.setattr(httpx, "get", fake_get)
    handler_for("plugins")(Context(), "list agent:alpha")
    assert captured["params"] == {"scope": "agent:alpha"}
    assert "no plugin overrides" in capsys.readouterr().out


def test_plugins_set_merges_with_stored_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> Response:
        return Response(SCOPE_CONFIG)

    def fake_put(url: str, **kwargs: Any) -> Response:
        calls.append((url, kwargs))
        return Response(APPLY_RESULT)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "put", fake_put)

    assert handler_for("plugins")(Context(), "set api-rate-limit plugin.limit=5") is False

    payload = calls[0][1]["json"]
    assert payload["plugins"]["api-rate-limit"]["properties"] == {"plugin.limit": 5}
    assert payload["plugins"]["api-auth"] == {"enabled": True, "properties": {}}
    output = capsys.readouterr().out
    assert "applied: api-rate-limit" in output
    assert "restart required: api-log" in output


def test_plugins_disable_sets_enabled_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(SCOPE_CONFIG))
    def fake_put(url: str, **kwargs: Any) -> Response:
        calls.append(kwargs)
        return Response(APPLY_RESULT)

    monkeypatch.setattr(httpx, "put", fake_put)

    handler_for("plugins")(Context(), "disable api-auth")

    assert calls[0]["json"]["plugins"]["api-auth"]["enabled"] is False


def test_plugins_set_rejects_missing_pair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "set api-auth") is False
    assert "usage" in capsys.readouterr().out.lower()


def test_plugins_set_rejects_malformed_pair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "set api-auth broken") is False
    assert "KEY=VALUE" in capsys.readouterr().out


def test_plugins_history_lists_versions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response(HISTORY))
    assert handler_for("plugins")(Context(), "history api") is False
    output = capsys.readouterr().out
    assert "3 rollback cli" in output
    assert "target 1" in output


def test_plugins_rollback_posts_the_target_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> Response:
        calls.append(kwargs)
        return Response(APPLY_RESULT)

    monkeypatch.setattr(httpx, "post", fake_post)

    assert handler_for("plugins")(Context(), "rollback api 1") is False

    assert calls[0]["json"] == {"seq": 1, "actor": "cli"}
    assert calls[0]["params"] == {"scope": "api"}
    assert "applied: api-rate-limit" in capsys.readouterr().out


def test_plugins_rollback_requires_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "rollback") is False
    assert "usage" in capsys.readouterr().out.lower()


def test_plugins_reports_http_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response({"detail": "boom"}, 500))
    assert handler_for("plugins")(Context(), "list") is False
    assert "Plugin request failed" in capsys.readouterr().out


def test_plugins_without_arguments_prints_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "") is False
    assert "usage" in capsys.readouterr().out.lower()


def test_plugins_reports_unknown_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "explode") is False
    output = capsys.readouterr().out
    assert "Unknown /plugins action: explode" in output
    assert "usage" in output.lower()


def test_plugins_disable_requires_plugin_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "disable") is False
    assert "usage" in capsys.readouterr().out.lower()


def test_plugins_rollback_rejects_non_numeric_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert handler_for("plugins")(Context(), "rollback api latest") is False
    assert "usage" in capsys.readouterr().out.lower()


def test_plugins_rollback_uses_default_scope_for_bare_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> Response:
        calls.append(kwargs)
        return Response(APPLY_RESULT)

    monkeypatch.setattr(httpx, "post", fake_post)
    handler_for("plugins")(Context(), "rollback 2")
    assert calls[0]["params"] == {"scope": "api"}


def test_plugins_list_without_overrides_and_apply_without_targets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: Response({"scope": "api", "version": 1, "plugins": {}})
    )
    monkeypatch.setattr(
        httpx,
        "put",
        lambda url, **kwargs: Response({"scope": "api", "version": 2}),
    )
    handler_for("plugins")(Context(), "list")
    handler_for("plugins")(Context(), "set api-auth plugin.token=x")
    output = capsys.readouterr().out
    assert "no plugin overrides" in output
    assert "applied: -" in output
