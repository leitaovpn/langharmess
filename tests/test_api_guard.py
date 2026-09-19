"""Unit tests for the API-server guard owned by the unified bootstrap."""
# mypy: ignore-errors
# pyright: reportArgumentType=false

from __future__ import annotations

import sys

import pytest

import langharness.api_guard as api_guard_module
from langharness.api_guard import APIGuard


def test_api_guard_is_running_accepts_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 401

    monkeypatch.setattr(api_guard_module.httpx, "get", lambda *a, **k: Response())
    assert APIGuard().is_running() is True


def test_api_guard_is_running_rejects_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 503

    monkeypatch.setattr(api_guard_module.httpx, "get", lambda *a, **k: Response())
    assert APIGuard().is_running() is False


def test_api_guard_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        def terminate(self) -> None:
            pass

        def poll(self) -> None:
            return None

    process = FakeProcess()
    commands = []
    monkeypatch.setattr(
        api_guard_module.subprocess,
        "Popen",
        lambda command: commands.append(command) or process,
    )
    monkeypatch.setattr(api_guard_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        api_guard_module.time,
        "monotonic",
        lambda: [0.0, 0.1][0],
    )

    guard = APIGuard()
    states = [False, True]
    guard.is_running = lambda: states.pop(0)  # type: ignore[method-assign]
    guard.ensure_api_server()
    assert guard._process is process
    assert commands == [
        [
                sys.executable,
                "-m",
                "langharness",
                "--mode",
                "server",
                "--server-ip",
                "127.0.0.1",
                "--server-port",
                "11534",
        ]
    ]


def test_api_guard_uses_frozen_executable_to_start_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langharness.__main__ as bootstrap_main_module

    calls = []
    monkeypatch.setattr(api_guard_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        bootstrap_main_module,
        "main",
        lambda argv=None: calls.append(argv) or 0,
    )
    guard = APIGuard("http://127.0.0.1:9123")
    states = [False, True]
    guard.is_running = lambda: states.pop(0)  # type: ignore[method-assign]

    guard.ensure_api_server()

    assert calls == [
        [
            "--mode",
            "server",
            "--server-ip",
            "127.0.0.1",
            "--server-port",
            "9123",
        ]
    ]
    assert guard._process is None
