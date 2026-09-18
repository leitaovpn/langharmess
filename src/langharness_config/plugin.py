"""Descriptors and assembly helpers for the built-in configuration plugins."""

from __future__ import annotations

from pathlib import Path

from langharness_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS
from langharness_plugin.package import PluginContribution, PluginPackage
from langharness_plugin.registry import PluginDescriptor


def config_descriptors(directory: str | None = None) -> list[PluginDescriptor]:
    properties = (
        {"plugin.config.path": str(Path(directory).expanduser() / "langharness.toml")}
        if directory
        else {}
    )
    return [
        PluginDescriptor(
            name="config-toml",
            version="1.0.0",
            module="langharness_config.plugins.toml",
            factory="toml-config-plugin-factory",
            instance="config-toml",
            specification=SPEC_CONFIG_PROVIDER,
            properties=properties,
            scope="root",
        ),
        PluginDescriptor(
            name="configs",
            version="1.0.0",
            module="langharness_config.plugins.configs",
            factory="configs-plugin-factory",
            instance="configs",
            specification=SPEC_CONFIGS,
            scope="root",
        ),
    ]


def builtin_package() -> PluginPackage:
    """Describe the built-in configuration plugins."""
    config_toml, configs = config_descriptors()
    return PluginPackage(
        id="builtin.config",
        version="1.0.0",
        contributions=(
            PluginContribution("toml", "root", config_toml),
            PluginContribution("configs", "root", configs),
        ),
    )
