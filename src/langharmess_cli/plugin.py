"""Descriptors and assembly helpers for the built-in CLI plugins."""

from __future__ import annotations

from langharmess_cli.contracts import SPEC_CLI_COMMAND, SPEC_CLI_RENDERER
from langharmess_plugin.registry import PluginDescriptor


def cli_descriptors(locale: str) -> list[PluginDescriptor]:
    return [
        PluginDescriptor(
            name="cli-health",
            version="1.0.0",
            module="langharmess_cli.plugins.commands.health",
            factory="cli-health-plugin-factory",
            instance="cli-health",
            specification=SPEC_CLI_COMMAND,
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-model",
            version="1.0.0",
            module="langharmess_cli.plugins.commands.model",
            factory="cli-model-command-factory",
            instance="cli-model",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-rich-renderer",
            version="1.0.0",
            module="langharmess_cli.plugins.rich_renderer",
            factory="rich-cli-renderer-factory",
            instance="cli-rich-renderer",
            specification=SPEC_CLI_RENDERER,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-session",
            version="1.0.0",
            module="langharmess_cli.plugins.commands.session",
            factory="cli-session-command-factory",
            instance="cli-session",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-plugins",
            version="1.0.0",
            module="langharmess_cli.plugins.commands.plugins",
            factory="cli-plugins-command-factory",
            instance="cli-plugins",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-shell",
            version="1.0.0",
            module="langharmess_cli.plugins.commands.shell",
            factory="cli-shell-command-factory",
            instance="cli-shell",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
    ]
