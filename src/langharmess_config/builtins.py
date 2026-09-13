"""Descriptors for the built-in configuration service chain."""

from __future__ import annotations

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS
from langharmess_plugin.registry import PluginDescriptor


def config_descriptors(config_path: str | None = None) -> list[PluginDescriptor]:
    properties = {"plugin.config.path": config_path} if config_path else {}
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
