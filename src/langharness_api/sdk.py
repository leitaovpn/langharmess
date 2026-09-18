"""Replaceable REST SDK package selected by the unified bootstrap."""

from langharness_api.plugin import sdk_package
from langharness_plugin.package import PluginPackage


def package() -> PluginPackage:
    return sdk_package()

