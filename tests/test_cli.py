"""Unit tests for the plugin-driven CLI."""
# mypy: ignore-errors
# pyright: reportArgumentType=false

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import langharmess_cli.__main__ as main_module
from langharmess_cli import api_guard as api_guard_module
from langharmess_cli.api_guard import APIGuard
from langharmess_cli.contracts import CLICommandProvider, CommandSpec
from langharmess_cli.plugins.commands.template_health import TemplateHealthCommandPlugin
from langharmess_cli.runner import CLIRunner


def test_command_spec_defaults() -> None:
    def handler(_args) -> int:
        return 0

    spec = CommandSpec(name="health", help="check health", handler=handler)
    assert spec.name == "health"
    assert spec.help == "check health"
    assert spec.handler({}) == 0


def test_runner_registers_and_executes_plugin_command() -> None:
    def handler(args) -> int:
        assert args.message == "hello"
        return 7

    def add_arguments(parser):
        parser.add_argument("--message", default="hello")

    spec = CommandSpec(
        name="greet",
        help="greet",
        handler=handler,
        add_arguments=add_arguments,
    )
    runner = CLIRunner([spec])
    assert runner.run(["greet"]) == 7


def test_template_health_command_provider_conforms() -> None:
    plugin = TemplateHealthCommandPlugin()
    assert isinstance(plugin, CLICommandProvider)
    commands = plugin.get_commands()
    assert [command.name for command in commands] == ["health"]


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
    monkeypatch.setattr(api_guard_module.subprocess, "Popen", lambda *a, **k: process)
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


def test_health_command_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import langharmess_cli.plugins.commands.template_health as health_module

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
    args = type("Args", (), {"base_url": "http://127.0.0.1:8000"})()
    assert plugin._handler(args) == 0
    assert "{'status': 'ok'}" in capsys.readouterr().out


def test_main_runs_plugin_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["langharmess", "health"])

    command = CommandSpec(name="health", help="check", handler=lambda args: 9)
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=lambda descriptor: None,
        get_services=lambda spec: [
            SimpleNamespace(get_commands=lambda: [command])
        ],
    )
    monkeypatch.setattr(
        main_module,
        "PluginManager",
        lambda registry: manager,
    )
    monkeypatch.setattr(
        main_module,
        "PluginRegistry",
        lambda descriptors: SimpleNamespace(list=lambda: descriptors),
    )
    monkeypatch.setattr(main_module, "CLIRunner", lambda commands: CLIRunner(commands))

    assert main_module.main() == 9


def test_main_runs_interactive_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["langharmess"])

    provider = SimpleNamespace(
        get_commands=lambda: [],
        get_interactive_commands=lambda: [],
    )
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=lambda descriptor: None,
        get_services=lambda spec: [provider],
    )

    class FakeGuard:
        def __init__(self, base_url):
            self.base_url = base_url

        def ensure_api_server(self):
            return None

    class FakeInteractive:
        def __init__(self, *, base_url, token, commands):
            self.base_url = base_url
            self.token = token
            self.commands = commands

        def cmdloop(self):
            self.called = True

    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(
        main_module,
        "PluginRegistry",
        lambda descriptors: SimpleNamespace(list=lambda: descriptors),
    )
    monkeypatch.setattr(main_module, "APIGuard", FakeGuard)
    monkeypatch.setattr(main_module, "InteractiveCLIRunner", FakeInteractive)

    assert main_module.main() == 0


def test_main_installs_shell_command_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["langharmess"])
    installed = []
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=installed.append,
        get_services=lambda spec: [],
    )
    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(main_module, "APIGuard", lambda base_url: SimpleNamespace(ensure_api_server=lambda: None))
    monkeypatch.setattr(main_module.InteractiveCLIRunner, "cmdloop", lambda self: None)

    assert main_module.main() == 0
    assert {descriptor.name for descriptor in installed} == {"cli-health", "cli-shell"}
