"""Built-in interactive shell command plugin."""

from __future__ import annotations

from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_cli.contracts import (
    SPEC_CLI_COMMAND,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)


@ComponentFactory("cli-shell-command-factory")
@Provides(SPEC_CLI_COMMAND)
@Property("_plugin_name", "plugin.name", "shell-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
class ShellCommandPlugin:
    """Provides shell-local commands without coupling the runner to them."""

    def __init__(self) -> None:
        self._plugin_name = "shell-command"
        self._plugin_version = "1.0.0"

    def get_commands(self) -> list[CommandSpec]:
        return []

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="exit",
                help="Exit the interactive shell",
                handler=self._exit,
            ),
            InteractiveCommandSpec(
                name="help",
                help="Show available interactive commands",
                handler=self._help,
            ),
        ]

    def _exit(self, context: InteractiveCommandContext, line: str) -> bool:
        return True

    def _help(self, context: InteractiveCommandContext, line: str) -> bool:
        if line:
            command = context.commands.get(line)
            if command is None:
                print(f"Unknown command: /{line}")
            else:
                print(f"/{command.name}: {command.help}")
            return False

        for command in sorted(context.commands.values(), key=lambda item: item.name):
            print(f"/{command.name:<12} {command.help}")
        return False

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
