"""Rich interactive renderer tests."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from langharmess_cli.contracts import InteractiveRenderer
from langharmess_cli.plugins.rich_renderer import RichInteractiveRenderer


def make_renderer() -> tuple[RichInteractiveRenderer, StringIO]:
    output = StringIO()
    renderer = RichInteractiveRenderer()
    renderer.console = Console(file=output, force_terminal=False, width=100)
    return renderer, output


def test_rich_renderer_conforms_and_renders_markdown_and_tools() -> None:
    renderer, output = make_renderer()
    assert isinstance(renderer, InteractiveRenderer)

    renderer.start_response()
    renderer.render_event({"type": "assistant", "content": "**hello**"})
    renderer.render_event(
        {"type": "tool_call", "name": "bash", "args": {"commands": "pwd"}}
    )
    renderer.render_event(
        {"type": "tool_output", "name": "bash", "output": "/workspace"}
    )
    renderer.finish_response()

    rendered = output.getvalue()
    assert "hello" in rendered
    assert "[tool call] bash {'commands': 'pwd'}" in rendered
    assert "[tool output] bash: /workspace" in rendered


def test_rich_renderer_renders_welcome_and_errors() -> None:
    renderer, output = make_renderer()
    renderer.show_welcome("Use /help")
    renderer.show_error("broken")
    assert "langharmess" in output.getvalue()
    assert "Use /help" in output.getvalue()
    assert "Error: broken" in output.getvalue()
