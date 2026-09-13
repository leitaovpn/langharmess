"""Rich interactive renderer tests."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from rich.console import Console

import langharmess_cli.plugins.rich_renderer as renderer_module
from langharmess_cli.contracts import InteractiveRenderer
from langharmess_cli.plugins.rich_renderer import RichInteractiveRenderer

USAGE = {"type": "usage", "input_tokens": 10, "output_tokens": 2, "total_tokens": 12}


def make_renderer(terminal: bool = False) -> tuple[RichInteractiveRenderer, StringIO]:
    output = StringIO()
    renderer = RichInteractiveRenderer()
    renderer.console = Console(file=output, force_terminal=terminal, width=100)
    return renderer, output


def render_plain(renderable: Any, width: int = 100) -> str:
    output = StringIO()
    Console(file=output, force_terminal=False, color_system=None, width=width).print(
        renderable
    )
    return output.getvalue()


def patch_clock(monkeypatch: pytest.MonkeyPatch, values: list[float]) -> None:
    clock = iter(values)
    monkeypatch.setattr(renderer_module.time, "monotonic", lambda: next(clock))


def test_renderer_conforms_to_protocol() -> None:
    assert isinstance(RichInteractiveRenderer(), InteractiveRenderer)


def test_renderer_renders_welcome_and_localized_errors() -> None:
    renderer, output = make_renderer()
    renderer.show_welcome("Use /help")
    renderer.show_error("broken")
    rendered = output.getvalue()
    assert "langharmess" in rendered
    assert "Use /help" in rendered
    assert "Error: broken" in rendered

    zh, zh_output = make_renderer()
    zh._locale = "zh"
    zh.show_error("坏了")
    assert "错误: 坏了" in zh_output.getvalue()


def test_plain_path_appends_assistant_text_without_reprinting() -> None:
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "hel"})
    renderer.render_event({"type": "assistant", "content": "lo"})
    renderer.finish_response()
    rendered = output.getvalue()
    assert rendered.count("hello") == 1
    assert rendered.endswith("hello")


def test_plain_path_does_not_interpret_markup() -> None:
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "**bold** [x]"})
    renderer.finish_response()
    assert "**bold** [x]" in output.getvalue()


def test_plain_path_renders_tool_rows_with_duration_and_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_clock(monkeypatch, [100.0, 100.25])
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "tool_call_id": "call-1", "args": {"commands": "pwd"}}
    )
    renderer.render_event(
        {"type": "tool_output", "name": "bash", "tool_call_id": "call-1", "output": "f" * 2400}
    )
    renderer.finish_response()
    rendered = output.getvalue()
    assert "+ bash {'commands': 'pwd'}" in rendered
    assert "✓ bash (250ms · 2.3KB)" in rendered


def test_plain_path_matches_output_to_running_tool_without_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_clock(monkeypatch, [0.0, 0.01])
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event({"type": "tool_call", "name": "bash", "args": {"commands": "pwd"}})
    renderer.render_event({"type": "tool_output", "name": "bash", "output": "/workspace"})
    renderer.finish_response()
    rendered = output.getvalue()
    assert "+ bash {'commands': 'pwd'}" in rendered
    assert "✓ bash (10ms · 10B)" in rendered


def test_plain_path_marks_error_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_clock(monkeypatch, [0.0, 0.01])
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "tool_call_id": "c1", "args": "x"}
    )
    renderer.render_event(
        {"type": "tool_output", "name": "bash", "tool_call_id": "c1", "output": "Error: boom"}
    )
    renderer.finish_response()
    assert "✗ bash (error)" in output.getvalue()


def test_unknown_events_are_ignored() -> None:
    renderer, output = make_renderer()
    renderer.start_response()
    renderer.render_event({"type": "mystery", "content": "??"})
    renderer.finish_response()
    assert output.getvalue() == ""


def test_usage_accumulates_across_responses_into_status_text() -> None:
    renderer, _ = make_renderer()
    renderer.set_model("deepseek-v4-flash")
    assert renderer.get_status_text() == " deepseek-v4-flash · /help for commands "
    renderer.start_response()
    renderer.render_event(USAGE)
    renderer.finish_response()
    renderer.start_response()
    renderer.render_event(USAGE)
    renderer.finish_response()
    assert (
        renderer.get_status_text()
        == " deepseek-v4-flash · 24 tokens · /help for commands "
    )


def test_status_text_is_localized() -> None:
    renderer, _ = make_renderer()
    renderer._locale = "zh"
    renderer.set_model("deepseek-v4-flash")
    renderer.start_response()
    renderer.render_event(USAGE)
    renderer.finish_response()
    assert (
        renderer.get_status_text()
        == " deepseek-v4-flash · 12 令牌 · /help 查看命令 "
    )


def test_status_line_shows_thinking_then_usage() -> None:
    renderer, _ = make_renderer()
    renderer.set_model("m1")
    renderer.start_response()
    assert renderer._status_line() == "⠋ thinking… · m1"
    renderer.render_event(USAGE)
    assert renderer._status_line() == "⠋ thinking… · m1 · 10 in / 2 out"


def test_status_line_shows_running_tool() -> None:
    renderer, _ = make_renderer()
    renderer.set_model("m1")
    renderer.start_response()
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "tool_call_id": "c1", "args": {"commands": "pwd"}}
    )
    assert renderer._status_line() == "⠋ bash {'commands': 'pwd'} · m1"


def test_tool_lines_render_running_done_error_states() -> None:
    renderer, _ = make_renderer()
    running = renderer_module._ToolRun(name="bash", args_summary="pwd", started=0.0)
    running_line = render_plain(renderer._tool_line(running))
    assert "bash" in running_line
    assert "pwd" in running_line
    done = renderer_module._ToolRun(
        name="bash",
        args_summary="",
        started=0.0,
        status="done",
        duration_ms=123,
        output_bytes=2048,
    )
    assert "✓ bash (123ms · 2.0KB)" in render_plain(renderer._tool_line(done))
    failed = renderer_module._ToolRun(name="bash", args_summary="", started=0.0, status="error")
    assert "✗ bash (error)" in render_plain(renderer._tool_line(failed))


def test_tool_args_are_summarized_to_one_line() -> None:
    renderer, _ = make_renderer()
    long_summary = " ".join(str({"a": "x" * 200}).split())
    assert renderer._summarize_args({"a": "x" * 200}) == long_summary[:60] + "…"
    assert renderer._summarize_args({"a": "short"}) == "{'a': 'short'}"


def test_token_and_size_formatting() -> None:
    renderer, _ = make_renderer()
    assert renderer._format_tokens(999) == "999"
    assert renderer._format_tokens(1000) == "1.0k"
    assert renderer._format_tokens(12400) == "12.4k"
    assert renderer._format_size(10) == "10B"
    assert renderer._format_size(2048) == "2.0KB"
    assert renderer._format_size(1572864) == "1.5MB"


def test_tty_path_runs_live_during_stream_and_stops_on_finish() -> None:
    renderer, output = make_renderer(terminal=True)
    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "hi"})
    assert renderer._live is not None
    assert renderer._status == "thinking"
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "tool_call_id": "c1", "args": "pwd"}
    )
    assert renderer._status == "tool"
    renderer.render_event(
        {"type": "tool_output", "name": "bash", "tool_call_id": "c1", "output": "/w"}
    )
    renderer.finish_response()
    assert renderer._live is None
    assert renderer._status == "idle"
    assert renderer._tool_runs["c1"].status == "done"


def test_frame_contains_markdown_tool_rows_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer, _ = make_renderer(terminal=True)
    monkeypatch.setattr(renderer, "_refresh", lambda force=False: None)
    renderer.set_model("m1")
    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "**hello**"})
    assert "thinking" in renderer._status_line()
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "tool_call_id": "c1", "args": {"commands": "pwd"}}
    )
    rendered = render_plain(renderer._build_frame())
    assert "hello" in rendered
    assert "bash" in rendered
    assert "m1" in rendered


def test_assistant_events_are_throttled_but_flushes_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_clock(monkeypatch, [0.0, 0.05, 0.05, 0.13, 0.26, 0.26])
    renderer, _ = make_renderer(terminal=True)
    frames = 0
    original = renderer._render_frame

    def counting() -> None:
        nonlocal frames
        frames += 1
        original()

    monkeypatch.setattr(renderer, "_render_frame", counting)
    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "a"})  # first always renders
    renderer.render_event({"type": "assistant", "content": "b"})  # throttled
    renderer.render_event(  # forces a frame
        {"type": "tool_call", "name": "bash", "tool_call_id": "c1", "args": "pwd"}
    )
    renderer.render_event({"type": "assistant", "content": "c"})  # window elapsed
    renderer.finish_response()  # flush forces a final frame
    assert frames == 4
