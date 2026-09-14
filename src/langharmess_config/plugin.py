"""Descriptors and assembly helpers for the built-in configuration plugins."""

from __future__ import annotations

from pathlib import Path

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS
from langharmess_plugin.registry import PluginDescriptor


def config_descriptors(directory: str | None = None) -> list[PluginDescriptor]:
    properties = (
        {"plugin.config.path": str(Path(directory).expanduser() / "langharmess.toml")}
        if directory
        else {}
    )
    return [
        PluginDescriptor(
            name="config-toml",
            version="1.0.0",
            module="langharmess_config.plugins.toml",
            factory="toml-config-plugin-factory",
            instance="config-toml",
            specification=SPEC_CONFIG_PROVIDER,
            properties=properties,
        ),
        PluginDescriptor(
            name="configs",
            version="1.0.0",
            module="langharmess_config.plugins.configs",
            factory="configs-plugin-factory",
            instance="configs",
            specification=SPEC_CONFIGS,
        ),
    ]
