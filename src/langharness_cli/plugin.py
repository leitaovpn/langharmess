"""Descriptors and assembly helpers for the built-in CLI plugins."""

from __future__ import annotations

from langharness_cli.contracts import (
    SPEC_CLI_COMMAND,
    SPEC_CLI_RENDERER,
    SPEC_UI_SERVER,
)
from langharness_plugin.package import PluginContribution, PluginPackage
from langharness_plugin.registry import PluginDescriptor


def cli_descriptors(locale: str) -> list[PluginDescriptor]:
    return [
        PluginDescriptor(
            name="ui-server",
            version="1.0.0",
            module="langharness_cli.plugins.server",
            factory="ui-server-factory",
            instance="ui-server",
            specification=SPEC_UI_SERVER,
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-health",
            version="1.0.0",
            module="langharness_cli.plugins.commands.health",
            factory="cli-health-plugin-factory",
            instance="cli-health",
            specification=SPEC_CLI_COMMAND,
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-model",
            version="1.0.0",
            module="langharness_cli.plugins.commands.model",
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
            module="langharness_cli.plugins.rich_renderer",
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
            module="langharness_cli.plugins.commands.session",
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
            module="langharness_cli.plugins.commands.plugins",
            factory="cli-plugins-command-factory",
            instance="cli-plugins",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-scope",
            version="1.0.0",
            module="langharness_cli.plugins.commands.scope",
            factory="cli-scope-command-factory",
            instance="cli-scope",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
        PluginDescriptor(
            name="cli-shell",
            version="1.0.0",
            module="langharness_cli.plugins.commands.shell",
            factory="cli-shell-command-factory",
            instance="cli-shell",
            specification=SPEC_CLI_COMMAND,
            properties={"plugin.ui.locale": locale},
            scope="ui",
            scope_parent="root",
        ),
    ]


def builtin_package() -> PluginPackage:
    """Describe the CLI plugins already installed by the CLI assembly."""
    contribution_ids = (
        "server",
        "health",
        "model",
        "rich-renderer",
        "session",
        "plugins",
        "scope",
        "shell",
    )
    return PluginPackage(
        id="builtin.cli",
        version="1.0.0",
        contributions=tuple(
            PluginContribution(contribution_id, "ui", descriptor)
            for contribution_id, descriptor in zip(
                contribution_ids, cli_descriptors("en"), strict=True
            )
        ),
    )
