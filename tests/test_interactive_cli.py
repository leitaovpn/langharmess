"""Tests for interactive CLI mode."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false
# pyright: reportArgumentType=false

from __future__ import annotations

import json

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import fragment_list_to_text

import langharmess_cli.plugins.commands.health as health_module
from langharmess_cli.common.interactive import InteractiveCLIRunner
from langharmess_cli.contracts import InteractiveCommandSpec
from langharmess_cli.plugins.commands.health import HealthCommandPlugin
from langharmess_cli.plugins.commands.shell import ShellCommandPlugin
from langharmess_cli.plugins.rich_renderer import RichInteractiveRenderer


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
    monkeypatch.delenv("LANG_HARMESS_STREAM_USAGE", raising=False)

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

    monkeypatch.setattr("langharmess_cli.common.interactive.httpx.stream", fake_stream)
    runner = InteractiveCLIRunner(
        base_url="http://127.0.0.1:8000",
        token="secret",
        model="deepseek-v4-flash",
        api_key="model-secret",
        model_base_url="https://models.example/v1/",
        commands=[],
        session_id="cli-session",
    )
    runner.do_stream("hello")
    output = capsys.readouterr().out
    assert "+ bash {'commands': 'pwd'}" in output
    assert "✓ bash (" in output
    assert "10B" in output
    assert "done" in output
    assert captured["json"] == {
        "input": "hello",
        "model": "deepseek-v4-flash",
        "protocol": "chat",
        "api_key": "model-secret",
        "base_url": "https://models.example/v1",
        "session_id": "cli-session",
        "user_id": "local_user",
        "agent_id": "simple_agent",
    }


def stream_response(lines: list[dict]) -> object:
    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return [json.dumps(line) for line in lines]

    return FakeStreamResponse()


def test_interactive_runner_sends_explicit_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        return stream_response([])

    monkeypatch.setattr("langharmess_cli.common.interactive.httpx.stream", fake_stream)
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[],
        user_id="alice",
        agent_id="researcher",
        session_id="pinned-session",
    )
    runner.do_stream("hi")
    assert captured["json"]["user_id"] == "alice"
    assert captured["json"]["agent_id"] == "researcher"
    assert captured["json"]["session_id"] == "pinned-session"


def test_interactive_runner_omits_session_id_until_server_assigns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        return stream_response([])

    monkeypatch.setattr("langharmess_cli.common.interactive.httpx.stream", fake_stream)
    runner = InteractiveCLIRunner(
        base_url="http://api", token="secret", commands=[], session_id=None
    )
    runner.do_stream("hi")
    assert "session_id" not in captured["json"]


def test_interactive_runner_adopts_session_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "langharmess_cli.common.interactive.httpx.stream",
        lambda *a, **k: stream_response(
            [
                {
                    "type": "session",
                    "session_id": "server-session",
                    "agent_id": "researcher",
                    "user_id": "local_user",
                },
                {"type": "assistant", "content": "done"},
            ]
        ),
    )
    renderer = RecordingRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[],
        renderer=renderer,
        session_id=None,
    )
    runner.do_stream("hello")

    assert runner.session_id == "server-session"
    assert runner.agent_id == "researcher"
    assert {"type": "assistant", "content": "done"} in renderer.events
    assert all(event.get("type") != "session" for event in renderer.events)


def test_interactive_runner_forwards_identity_to_real_renderer_status() -> None:
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[],
        renderer=RichInteractiveRenderer(),
        user_id="alice",
        agent_id="researcher",
        session_id="abcdef1234567890",
    )
    status = runner.renderer.get_status_text()
    assert "alice@researcher" in status
    assert "abcdef12" in status
    assert "gpt-4o-mini" in status


def test_health_provides_interactive_command() -> None:
    plugin = HealthCommandPlugin()
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


def test_shell_plugin_localizes_help_in_zh(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin = ShellCommandPlugin()
    plugin._locale = "zh"
    commands = plugin.get_interactive_commands()
    help_texts = {command.name: command.help for command in commands}
    assert help_texts["exit"] == "退出交互式 shell"
    assert help_texts["help"] == "显示可用的交互命令"

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
    assert runner.onecmd("/help missing") is False
    assert "未知命令: /missing" in capsys.readouterr().out


def test_health_interactive_handler(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Response:
        status_code = 200

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(health_module.httpx, "get", lambda *a, **k: Response())

    plugin = HealthCommandPlugin()
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


class RecordingRenderer:
    def __init__(self):
        self.welcome = ""
        self.errors = []
        self.events = []

    def show_welcome(self, text):
        self.welcome = text

    def start_response(self):
        return None

    def render_event(self, event):
        self.events.append(event)

    def finish_response(self):
        return None

    def show_error(self, message):
        self.errors.append(message)


def test_cmdloop_uses_dynamic_status_toolbar_with_real_renderer() -> None:
    prompts = []

    class FakeSession:
        def prompt(self, *args, **kwargs):
            prompts.append((args, kwargs))
            return "/exit"

    renderer = RichInteractiveRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=ShellCommandPlugin().get_interactive_commands(),
        renderer=renderer,
        session=FakeSession(),
    )
    runner._interactive_input = True
    runner.cmdloop()
    toolbar = prompts[0][1]["bottom_toolbar"]
    assert callable(toolbar)
    assert toolbar().startswith(
        " local_user@simple_agent · new session · environment · gpt-4o-mini · chat"
    )


def test_runner_localizes_welcome_and_unknown_command_in_zh() -> None:
    class FakeSession:
        def prompt(self, *args, **kwargs):
            return "/exit"

    renderer = RecordingRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=ShellCommandPlugin().get_interactive_commands(),
        renderer=renderer,
        locale="zh",
        session=FakeSession(),
    )
    runner._interactive_input = True
    runner.cmdloop()
    assert renderer.welcome == "输入消息开始对话。\n/help 查看命令 · /exit 安全退出"
    runner.onecmd("/missing")
    assert renderer.errors == ["未知命令: /missing。输入 /help 查看可用命令。"]


def test_runner_localizes_cancelled_in_zh(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(
        "langharmess_cli.common.interactive.httpx.stream", lambda *a, **k: Response()
    )
    renderer = RecordingRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=[],
        renderer=renderer,
        locale="zh",
    )
    runner.do_stream("hi")
    assert renderer.errors == ["已取消"]


def test_runner_forwards_usage_events_to_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usage = {
        "type": "usage",
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
    }

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return [json.dumps(usage)]

    monkeypatch.setattr(
        "langharmess_cli.common.interactive.httpx.stream", lambda *a, **k: FakeStreamResponse()
    )
    renderer = RecordingRenderer()
    runner = InteractiveCLIRunner(
        base_url="http://api", token="secret", commands=[], renderer=renderer
    )
    runner.do_stream("hi")
    assert usage in renderer.events


def test_runner_sends_stream_usage_escape_hatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return []

    captured = {}

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        return FakeStreamResponse()

    monkeypatch.setattr("langharmess_cli.common.interactive.httpx.stream", fake_stream)
    monkeypatch.setenv("LANG_HARMESS_STREAM_USAGE", "false")
    runner = InteractiveCLIRunner(base_url="http://api", token="secret", commands=[])
    runner.do_stream("hi")
    assert captured["json"]["stream_usage"] is False
