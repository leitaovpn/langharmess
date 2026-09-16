"""Replaceable REST SDK package selected by the unified bootstrap."""

from langharmess_api.plugin import sdk_package
from langharmess_plugin.package import PluginPackage


def package() -> PluginPackage:
    return sdk_package()

