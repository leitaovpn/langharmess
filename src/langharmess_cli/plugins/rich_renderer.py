"""Rich renderer for the interactive CLI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Property, Provides
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from langharmess_cli.contracts import SPEC_CLI_RENDERER


@ComponentFactory("rich-cli-renderer-factory")
@Provides(SPEC_CLI_RENDERER)
@Property("_plugin_name", "plugin.name", "rich-renderer")
@Property("_plugin_version", "plugin.version", "1.0.0")
class RichInteractiveRenderer:
    """Renders conversation events while keeping transport details out of the UI."""

    def __init__(self) -> None:
        self._plugin_name = "rich-renderer"
        self._plugin_version = "1.0.0"
        self.console = Console()
        self._assistant_text = ""
        self._live: Live | None = None

    def show_welcome(self, text: str) -> None:
        self.console.print(
            Panel.fit(text, title="[bold cyan]langharmess[/bold cyan]", border_style="cyan")
        )

    def start_response(self) -> None:
        self._assistant_text = ""
        self._live = None

    def render_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "assistant":
            self._assistant_text += str(event.get("content", ""))
            markdown = Markdown(self._assistant_text)
            if self._live is None:
                self._live = Live(
                    markdown,
                    console=self.console,
                    refresh_per_second=12,
                    vertical_overflow="visible",
                )
                self._live.start(refresh=True)
            else:
                self._live.update(markdown, refresh=True)
            return
        if event_type == "tool_call":
            self._flush_assistant()
            self.console.print(
                Panel(
                    Text(f"[tool call] {event.get('name')} {event.get('args')}"),
                    border_style="yellow",
                )
            )
            return
        if event_type == "tool_output":
            self._flush_assistant()
            self.console.print(
                Panel(
                    Text(
                        f"[tool output] {event.get('name')}: {event.get('output')}"
                    ),
                    border_style="green",
                )
            )

    def finish_response(self) -> None:
        self._flush_assistant()

    def show_error(self, message: str) -> None:
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def _flush_assistant(self) -> None:
        if self._live is not None:
            self._live.stop()
        self._live = None
        self._assistant_text = ""

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
