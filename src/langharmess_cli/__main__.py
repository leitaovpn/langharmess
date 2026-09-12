"""Command-line entrypoint."""

from __future__ import annotations

import sys

from langharmess_cli.api_guard import APIGuard
from langharmess_cli.contracts import SPEC_CLI_COMMAND
from langharmess_cli.interactive import InteractiveCLIRunner
from langharmess_cli.runner import CLIRunner
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry


def main() -> int:
    registry = PluginRegistry(
        [
            PluginDescriptor(
                name="cli-health",
                version="1.0.0",
                module="langharmess_cli.plugins.commands.template_health",
                factory="cli-health-command-factory",
                instance="cli-health",
                specification=SPEC_CLI_COMMAND,
            )
        ]
    )
    manager = PluginManager(registry)
    manager.start()
    try:
        for descriptor in registry.list():
            manager.install_plugin(descriptor)

        providers = manager.get_services(SPEC_CLI_COMMAND)
        commands = [
            command
            for provider in providers
            for command in provider.get_commands()
        ]

        if len(sys.argv) == 1 or sys.argv[1] == "interactive":
            base_url = "http://127.0.0.1:8000"
            token = "secret"
            interactive_args = (
                sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "interactive" else sys.argv[1:]
            )
            for index, arg in enumerate(interactive_args):
                if arg == "--base-url" and index + 1 < len(interactive_args):
                    base_url = interactive_args[index + 1]
                elif arg.startswith("--base-url="):
                    base_url = arg.split("=", 1)[1]
                elif arg == "--token" and index + 1 < len(interactive_args):
                    token = interactive_args[index + 1]
                elif arg.startswith("--token="):
                    token = arg.split("=", 1)[1]
            APIGuard(base_url).ensure_api_server()
            interactive_commands = [
                command
                for provider in providers
                for command in provider.get_interactive_commands()
            ]
            runner = InteractiveCLIRunner(
                base_url=base_url,
                token=token,
                commands=interactive_commands,
            )
            runner.cmdloop()
            return 0

        return CLIRunner(commands).run(sys.argv[1:])
    finally:
        manager.stop()


if __name__ == "__main__":
    raise SystemExit(main())
