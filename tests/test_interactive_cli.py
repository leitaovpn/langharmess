"""Tests for interactive CLI mode."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import json

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import fragment_list_to_text

import langharmess_cli.plugins.commands.template_health as health_module
from langharmess_cli.contracts import InteractiveCommandSpec
from langharmess_cli.interactive import InteractiveCLIRunner
from langharmess_cli.plugins.commands.shell import ShellCommandPlugin
from langharmess_cli.plugins.commands.template_health import TemplateHealthCommandPlugin


def test_interactive_command_spec() -> None:
    spec = InteractiveCommandSpec(
        name="health", help="check", handler=lambda context, line: False
    )
    assert spec.name == "health"
    runner = InteractiveCLIRunner(base_url="http://api", token="secret", commands=[])
    assert spec.handler(runner, "") is False


def test_interactive_runner_dispatches_slash_plugin_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = InteractiveCommandSpec(
        name="greet",
        help="Greet somebody",
        handler=lambda context, line: print(
            f"{context.base_url}:{context.token}:{line}"
        ),
    )
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[command],
    )
    assert runner.onecmd("/greet Ada") is False
    assert "http://127.0.0.1:8000:secret:Ada" in capsys.readouterr().out


def test_interactive_runner_reports_unknown_slash_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = InteractiveCLIRunner(base_url="http://api", token="secret", commands=[])
    assert runner.onecmd("/missing") is False
    assert "Unknown command: /missing" in capsys.readouterr().out


def test_interactive_runner_stream_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return [
                json.dumps(
                    {"type": "tool_call", "name": "bash", "args": {"commands": "pwd"}}
                ),
                json.dumps(
                    {"type": "tool_output", "name": "bash", "output": "/workspace"}
                ),
                json.dumps({"type": "assistant", "content": "done"}),
            ]

    captured = {}

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        return FakeStreamResponse()

    monkeypatch.setattr("langharmess_cli.interactive.httpx.stream", fake_stream)
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        model="deepseek-v4-flash",
        api_key="model-secret",
        model_base_url="https://models.example/v1/",
        commands=[],
    )
    runner.do_stream("hello")
    output = capsys.readouterr().out
    assert "[tool call] bash {'commands': 'pwd'}" in output
    assert "[tool output] bash: /workspace" in output
    assert "done" in output
    assert captured["json"] == {
        "input": "hello",
        "model": "deepseek-v4-flash",
        "api_key": "model-secret",
        "base_url": "https://models.example/v1",
        "session_id": runner.session_id,
    }


def test_template_health_provides_interactive_command() -> None:
    plugin = TemplateHealthCommandPlugin()
    commands = plugin.get_interactive_commands()
    assert [command.name for command in commands] == ["health"]


def test_interactive_runner_default_streams_non_slash(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        InteractiveCLIRunner,
        "do_stream",
        lambda self, line: print(f"stream:{line}"),
    )
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[],
    )
    runner.onecmd("hello agent")
    assert "stream:hello agent" in capsys.readouterr().out


def test_interactive_runner_ignores_empty_default() -> None:
    runner = InteractiveCLIRunner(base_url="http://api", token="secret", commands=[])
    assert runner.default("") is None


def test_interactive_runner_exit_commands() -> None:
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        commands=[],
    )
    assert runner.do_exit("") is True
    assert runner.do_quit("") is True
    assert runner.do_EOF("") is True
    assert runner.onecmd("exit") is True
    assert runner.onecmd("quit") is True
    assert runner.onecmd("EOF") is True


def test_shell_plugin_provides_exit_and_dynamic_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    commands = ShellCommandPlugin().get_interactive_commands()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[
            *commands,
            InteractiveCommandSpec(
                name="health", help="Check health", handler=lambda context, line: False
            ),
        ],
    )

    assert runner.onecmd("/help") is False
    output = capsys.readouterr().out
    assert "/exit" in output
    assert "/help" in output
    assert "/health" in output
    assert runner.onecmd("help") is False
    assert "/health" in capsys.readouterr().out
    assert runner.onecmd("/exit") is True

    assert runner.onecmd("/help health") is False
    assert "/health: Check health" in capsys.readouterr().out
    assert runner.onecmd("/help missing") is False
    assert "Unknown command: /missing" in capsys.readouterr().out

    plugin = ShellCommandPlugin()
    assert plugin.get_commands() == []
    assert plugin.get_plugin_info() == {"name": "shell-command", "version": "1.0.0"}


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
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000", token="secret", commands=[]
    )
    assert plugin._interactive_handler(runner, "") is False
    assert "{'status': 'ok'}" in capsys.readouterr().out


def test_interactive_runner_has_welcome_screen() -> None:
    welcome = InteractiveCLIRunner.intro
    assert welcome is not None
    assert "conversation" in welcome
    assert "/help" in welcome
    assert "/exit" in welcome


def test_prompt_completion_is_built_from_command_plugins() -> None:
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[
            InteractiveCommandSpec(
                name="health", help="check", handler=lambda context, line: False
            )
        ],
    )
    completions = list(
        runner._command_completer().get_completions(
            Document("/he", cursor_position=3), CompleteEvent()
        )
    )
    assert [completion.text for completion in completions] == ["/health"]
    assert fragment_list_to_text(completions[0].display_meta) == "check"


def test_cmdloop_uses_prompt_session_and_injected_renderer() -> None:
    prompts = []

    class FakeSession:
        def prompt(self, *args, **kwargs):
            prompts.append((args, kwargs))
            return "/exit"

    class FakeRenderer:
        def __init__(self):
            self.welcome = ""

        def show_welcome(self, text):
            self.welcome = text

        def start_response(self):
            return None

        def render_event(self, event):
            return None

        def finish_response(self):
            return None

        def show_error(self, message):
            return None

    renderer = FakeRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=ShellCommandPlugin().get_interactive_commands(),
        renderer=renderer,
        session=FakeSession(),
    )
    runner._interactive_input = True
    runner.cmdloop()

    assert "conversation" in renderer.welcome
    assert len(prompts) == 1
    assert prompts[0][1]["bottom_toolbar"].startswith(" gpt-4o-mini")
