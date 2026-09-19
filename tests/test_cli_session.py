"""Tests for CLI identity default resolution."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from langharness_cli.common.session import resolve_identity


class Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://api/sessions")
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(self.status_code)
            )


def latest_session_response(agent_id: str = "researcher") -> Response:
    return Response(
        {
            "user_id": "local_user",
            "sessions": [
                {
                    "session_id": "s9",
                    "last_agent_id": agent_id,
                    "turns": 3,
                }
            ],
        }
    )


def test_resolve_identity_uses_latest_session_and_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: latest_session_response()
    )
    assert resolve_identity("http://api", "secret", "local_user") == (
        "s9",
        "researcher",
    )


def test_resolve_identity_falls_back_to_defaults_without_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: Response({"user_id": "local_user", "sessions": []}),
    )
    assert resolve_identity("http://api", "secret", "local_user") == (
        None,
        "simple_agent",
    )


def test_resolve_identity_prefers_explicit_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: latest_session_response()
    )
    assert resolve_identity(
        "http://api", "secret", "local_user", agent_id="simple_agent"
    ) == ("s9", "simple_agent")


def test_resolve_identity_prefers_explicit_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: latest_session_response()
    )
    assert resolve_identity(
        "http://api", "secret", "local_user", session_id="pinned"
    ) == ("pinned", "researcher")


def test_resolve_identity_new_session_keeps_default_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: latest_session_response()
    )
    assert resolve_identity("http://api", "secret", "local_user", new_session=True) == (
        None,
        "researcher",
    )


def test_resolve_identity_ignores_empty_last_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: Response(
            {"sessions": [{"session_id": "s1", "last_agent_id": ""}]}
        ),
    )
    assert resolve_identity("http://api", "secret", "local_user") == (
        "s1",
        "simple_agent",
    )


def test_resolve_identity_survives_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fail)
    assert resolve_identity("http://api", "secret", "local_user") == (
        None,
        "simple_agent",
    )


def test_resolve_identity_queries_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return latest_session_response()

    monkeypatch.setattr(httpx, "get", fake_get)
    resolve_identity("http://api/", "secret", "local_user")

    assert captured["url"] == "http://api/sessions"
    assert captured["params"] == {"user_id": "local_user", "limit": 1}
    assert captured["headers"] == {"Authorization": "Bearer secret"}
