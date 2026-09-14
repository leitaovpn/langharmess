"""Unit tests for the plugin-driven CLI."""
# mypy: ignore-errors
# pyright: reportArgumentType=false

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

import langharmess_cli.common.api_guard as api_guard_module
import langharmess_cli.common.cli as main_module
from langharmess_cli.common.api_guard import APIGuard
from langharmess_cli.common.runner import CLIRunner
from langharmess_cli.contracts import CLICommandProvider, CommandSpec
from langharmess_cli.plugins.commands.health import HealthCommandPlugin


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
    help_text = runner.build_parser().format_help()
    assert "--dir" in help_text
    assert "--log" not in help_text


def test_health_command_provider_conforms() -> None:
    plugin = HealthCommandPlugin()
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
            "langharmess_api",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
    ]


def test_api_guard_uses_frozen_executable_to_start_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langharmess_api.__main__ as api_main_module

    calls = []
    monkeypatch.setattr(api_guard_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        api_main_module,
        "main",
        lambda argv=None: calls.append(argv) or 0,
    )
    guard = APIGuard("http://127.0.0.1:9123")
    states = [False, True]
    guard.is_running = lambda: states.pop(0)  # type: ignore[method-assign]

    guard.ensure_api_server()

    assert calls == [["--host", "127.0.0.1", "--port", "9123"]]
    assert guard._process is None


def test_api_server_entrypoint_runs_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    import langharmess_api.__main__ as api_main_module
    import langharmess_api.common.server as server_module

    app = object()
    captured = {}
    monkeypatch.setattr(server_module, "create_app", lambda: app)
    monkeypatch.setattr(uvicorn, "run", lambda target, **kwargs: captured.update(
        target=target, **kwargs
    ))
    monkeypatch.setattr(
        sys, "argv", ["langharmess_api", "--host", "0.0.0.0", "--port", "9123"]
    )
    assert api_main_module.main() == 0
    assert captured == {
        "target": app,
        "host": "0.0.0.0",
        "port": 9123,
        "log_config": None,
    }


def test_health_command_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import langharmess_cli.plugins.commands.health as health_module

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

    plugin = HealthCommandPlugin()
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
        get_services=lambda spec: [SimpleNamespace(get_commands=lambda: [command])],
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
    monkeypatch.setenv("LANG_HARMESS_MODEL", "env-model")
    monkeypatch.setenv("LANG_HARMESS_API_KEY", "env-key")
    monkeypatch.setenv("LANG_HARMESS_BASE_URL", "https://models.example/v1")

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

    captured = {}

    class FakeInteractive:
        def __init__(
            self,
            *,
            base_url,
            token,
            model,
            provider_name,
            model_protocol,
            api_key,
            model_base_url,
            commands,
            renderer,
            history_file,
            locale,
        ):
            self.base_url = base_url
            self.token = token
            self.model = model
            self.api_key = api_key
            self.model_base_url = model_base_url
            self.commands = commands
            captured.update(
                model=model,
                provider_name=provider_name,
                model_protocol=model_protocol,
                api_key=api_key,
                model_base_url=model_base_url,
            )

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
    assert captured == {
        "model": "env-model",
        "provider_name": "environment",
        "model_protocol": "chat",
        "api_key": "env-key",
        "model_base_url": "https://models.example/v1",
    }


def test_main_passes_locale_flag_to_plugins_and_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANG_HARMESS_LOCALE", raising=False)
    monkeypatch.setattr(sys, "argv", ["langharmess", "interactive", "--locale", "zh"])
    installed = []
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=installed.append,
        get_services=lambda spec: [],
    )
    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(
        main_module,
        "APIGuard",
        lambda base_url: SimpleNamespace(ensure_api_server=lambda: None),
    )
    captured = {}

    class FakeInteractive:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def cmdloop(self):
            return None

    monkeypatch.setattr(main_module, "InteractiveCLIRunner", FakeInteractive)
    assert main_module.main() == 0
    renderer = next(d for d in installed if d.name == "cli-rich-renderer")
    shell = next(d for d in installed if d.name == "cli-shell")
    assert renderer.properties == {"plugin.ui.locale": "zh"}
    assert shell.properties == {"plugin.ui.locale": "zh"}
    assert captured["locale"] == "zh"


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
    monkeypatch.setattr(
        main_module,
        "APIGuard",
        lambda base_url: SimpleNamespace(ensure_api_server=lambda: None),
    )
    monkeypatch.setattr(main_module.InteractiveCLIRunner, "cmdloop", lambda self: None)

    assert main_module.main() == 0
    assert {descriptor.name for descriptor in installed} == {
        "cli-health",
        "cli-log",
        "cli-model",
        "cli-rich-renderer",
        "cli-shell",
        "config-toml",
        "configs",
    }


def test_main_uses_selected_provider_and_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "langharmess",
            "--provider",
            "demo",
            "--dir",
            str(tmp_path),
            "interactive",
        ],
    )
    configs = SimpleNamespace(
        get=lambda section, key: "configured.log",
        get_provider=lambda name: {
            "model": "provider-model",
            "api_key": "provider-key",
            "base_url": "https://provider.example/v1",
        },
    )
    command_provider = SimpleNamespace(
        get_commands=lambda: [], get_interactive_commands=lambda: []
    )
    log_messages = []
    log_provider = SimpleNamespace(
        get_logger=lambda: SimpleNamespace(info=log_messages.append)
    )
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=lambda descriptor: None,
        get_services=lambda spec: [command_provider],
        get_service=lambda spec: log_provider if spec == "log.plugin" else configs,
    )
    captured = {}

    class FakeInteractive:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def cmdloop(self):
            return None

    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(
        main_module,
        "PluginRegistry",
        lambda descriptors: SimpleNamespace(list=lambda: descriptors),
    )
    monkeypatch.setattr(
        main_module,
        "APIGuard",
        lambda base_url: SimpleNamespace(ensure_api_server=lambda: None),
    )
    monkeypatch.setattr(main_module, "InteractiveCLIRunner", FakeInteractive)
    assert main_module.main() == 0
    assert captured["model"] == "provider-model"
    assert captured["api_key"] == "provider-key"
    assert captured["model_base_url"] == "https://provider.example/v1"
    assert captured["commands"] == []
    assert log_messages == ["CLI started"]
    assert "LANG_HARMESS_DIR" not in os.environ


def test_main_randomly_selects_configured_provider_when_not_specified(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["langharmess", "--dir", str(tmp_path), "interactive"]
    )
    configs = SimpleNamespace(
        list_providers=lambda: ["first", "chosen"],
        get_provider=lambda name: {
            "model": f"{name}-model",
            "api_key": f"{name}-key",
            "base_url": f"https://{name}.example/v1",
        },
    )
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=lambda descriptor: None,
        get_services=lambda spec: [],
        get_service=lambda spec: configs if spec == "configs" else None,
    )
    captured = {}

    class FakeInteractive:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def cmdloop(self):
            return None

    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(
        main_module,
        "APIGuard",
        lambda base_url: SimpleNamespace(ensure_api_server=lambda: None),
    )
    monkeypatch.setattr(main_module, "InteractiveCLIRunner", FakeInteractive)
    monkeypatch.setattr(main_module.random, "choice", lambda names: names[-1])

    assert main_module.main() == 0
    assert captured["model"] == "chosen-model"
    assert captured["api_key"] == "chosen-key"
    assert captured["model_base_url"] == "https://chosen.example/v1"


def test_main_survives_broken_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langharmess_config.plugins.configs import ConfigsPlugin

    monkeypatch.setattr(sys, "argv", ["langharmess"])

    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(
            get_config=lambda: {
                "providers": {
                    "good": {"model": "demo", "api_key": "k"},
                    "broken": {"model": "demo", "api_key": "k", "protocol": "ftp"},
                }
            }
        )
    ]
    provider = SimpleNamespace(
        get_commands=lambda: [], get_interactive_commands=lambda: []
    )
    manager = SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        install_plugin=lambda descriptor: None,
        get_services=lambda spec: [provider],
        get_service=lambda spec: configs,
    )

    class FakeGuard:
        def __init__(self, base_url):
            self.base_url = base_url

        def ensure_api_server(self):
            return None

    monkeypatch.setattr(main_module, "PluginManager", lambda registry: manager)
    monkeypatch.setattr(
        main_module,
        "PluginRegistry",
        lambda descriptors: SimpleNamespace(list=lambda: descriptors),
    )
    monkeypatch.setattr(main_module, "APIGuard", FakeGuard)
    monkeypatch.setattr(
        main_module,
        "InteractiveCLIRunner",
        lambda **kwargs: SimpleNamespace(cmdloop=lambda: None),
    )

    assert main_module.main() == 0
