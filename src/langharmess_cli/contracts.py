"""Public contracts for CLI command plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

SPEC_CLI_COMMAND = "cli.plugin.command"
SPEC_CLI_RUNNER = "cli.runner"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: Callable[[Any], int]
    add_arguments: Callable[[Any], None] | None = None


@runtime_checkable
class CLICommandProvider(Protocol):
    def get_commands(self) -> list[CommandSpec]: ...

    def get_plugin_info(self) -> dict[str, str]: ...
