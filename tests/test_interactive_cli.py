"""Tests for interactive CLI mode."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import pytest

import langharmess_cli.plugins.commands.template_health as health_module
from langharmess_cli.contracts import InteractiveCommandSpec
from langharmess_cli.interactive import InteractiveCLIRunner
from langharmess_cli.plugins.commands.template_health import TemplateHealthCommandPlugin


def test_interactive_command_spec() -> None:
    spec = InteractiveCommandSpec(name="health", help="check", handler=lambda line: 0)
    assert spec.name == "health"
    assert spec.handler("") == 0


def test_interactive_runner_dispatches_plugin_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = []

    def handler(line: str) -> int:
        called.append(line)
        return 0

    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[InteractiveCommandSpec("greet", "greet", handler)],
    )
    runner.default("greet hello")
    assert called == ["hello"]


def test_interactive_runner_call_requests_api(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Response:
        status_code = 200

        def json(self):
            return {"echo": "ok"}

    monkeypatch.setattr(
        "langharmess_cli.interactive.httpx.get",
        lambda *args, **kwargs: Response(),
    )
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[],
    )
    runner.do_call("/echo")
    assert "{'echo': 'ok'}" in capsys.readouterr().out


def test_template_health_provides_interactive_command() -> None:
    plugin = TemplateHealthCommandPlugin()
    commands = plugin.get_interactive_commands()
    assert [command.name for command in commands] == ["health"]


def test_interactive_runner_unknown_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[],
    )
    runner.default("nope")
    assert "Unknown command: nope" in capsys.readouterr().out


def test_interactive_runner_exit_commands() -> None:
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[],
    )
    assert runner.do_exit("") is True
    assert runner.do_quit("") is True
    assert runner.do_EOF("") is True


def test_template_health_interactive_handler(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeGuard:
        def __init__(self, base_url):
            self.base_url = base_url

        def ensure_api_server(self):
            return None

    class Response:
        status_code = 200

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(health_module, "APIGuard", FakeGuard)
    monkeypatch.setattr(health_module.httpx, "get", lambda *a, **k: Response())

    plugin = TemplateHealthCommandPlugin()
    assert plugin._interactive_handler("") == 0
    assert "{'status': 'ok'}" in capsys.readouterr().out
