"""Descriptors for the built-in configuration service chain."""

from __future__ import annotations

from pathlib import Path

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS
from langharmess_plugin.registry import PluginDescriptor


def config_descriptors(directory: str | None = None) -> list[PluginDescriptor]:
    properties = (
        {"plugin.config.path": str(Path(directory).expanduser() / "langharmess.ini")}
        if directory
        else {}
    )
    return [
        PluginDescriptor(
            name="config-ini",
            version="1.0.0",
            module="langharmess_config.plugins.ini",
            factory="ini-config-plugin-factory",
            instance="config-ini",
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
