"""Command-line entrypoint."""

from __future__ import annotations

import sys

from langharmess_cli.contracts import SPEC_CLI_COMMAND
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
        return CLIRunner(commands).run(sys.argv[1:])
    finally:
        manager.stop()


if __name__ == "__main__":
    raise SystemExit(main())
