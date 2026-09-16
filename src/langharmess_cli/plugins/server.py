"""UI process entry service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pelix.ipopo.decorators import ComponentFactory, Provides

from langharmess_cli.contracts import UIServerProvider
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor


@ComponentFactory("ui-server-factory")
@Provides(UIServerProvider)
class UIServerService:
    def run(self, config: Mapping[str, Any]) -> int:
        from langharmess_cli.common.cli import main

        argv = list(cast(list[str], config.get("argv", [])))
        command = next((arg for arg in argv if not arg.startswith("-")), "interactive")
        config_dir = str(config["config_dir"])
        base_url = str(config["base_url"])
        if not any(arg == "--dir" or arg.startswith("--dir=") for arg in argv):
            argv[:0] = ["--dir", config_dir]
        if command in {"interactive", "health", "plugins"} and not any(
            arg == "--base-url" or arg.startswith("--base-url=") for arg in argv
        ):
            argv.extend(["--base-url", base_url])
        descriptors = cast(list[PluginDescriptor], config.get("descriptors", []))
        manager = cast(PluginManager | None, config.get("manager"))
        return main(argv, descriptors=descriptors, manager=manager)
