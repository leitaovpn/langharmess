"""Public contracts for CLI command plugins."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

SPEC_CLI_COMMAND = "cli.plugin.command"
SPEC_CLI_RUNNER = "cli.runner"
SPEC_CLI_RENDERER = "cli.plugin.renderer"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: Callable[[Any], int]
    add_arguments: Callable[[Any], None] | None = None


@dataclass(frozen=True)
class InteractiveCommandSpec:
    name: str
    help: str
    handler: Callable[[InteractiveCommandContext, str], bool | None]


@runtime_checkable
class InteractiveCommandContext(Protocol):
    """Runtime data exposed to interactive command plugins."""

    base_url: str
    token: str
    commands: Mapping[str, InteractiveCommandSpec]


@runtime_checkable
class CLICommandProvider(Protocol):
    def get_commands(self) -> list[CommandSpec]: ...

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class InteractiveRenderer(Protocol):
    def show_welcome(self, text: str) -> None: ...

    def start_response(self) -> None: ...

    def render_event(self, event: Mapping[str, Any]) -> None: ...

    def finish_response(self) -> None: ...

    def show_error(self, message: str) -> None: ...
