"""Health command plugin."""

from __future__ import annotations

from argparse import Namespace

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharness_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)


@ComponentFactory("cli-health-plugin-factory")
@Provides(CLICommandProvider)
@Property("_plugin_name", "plugin.name", "health-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_base_url", "plugin.base_url", "http://127.0.0.1:11534")
@Property("_token", "plugin.token", "secret")
class HealthCommandPlugin:
    def __init__(self) -> None:
        self._plugin_name = "health-command"
        self._plugin_version = "1.0.0"
        self._base_url = "http://127.0.0.1:11534"
        self._token = "secret"

    def _handler(self, args: Namespace) -> int:
        base_url = self._base_url.rstrip("/")
        response = httpx.get(
            f"{base_url}/health",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10.0,
        )
        print(response.json())
        return 0 if response.status_code == 200 else 1

    def get_commands(self) -> list[CommandSpec]:
        return [
            CommandSpec(
                name="health",
                help="Check the API server health",
                handler=self._handler,
            )
        ]

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="health",
                help="Check the API server health",
                handler=self._interactive_handler,
            )
        ]

    def _interactive_handler(
        self, context: InteractiveCommandContext, line: str
    ) -> bool:
        base_url = context.base_url.rstrip("/")
        response = httpx.get(
            f"{base_url}/health",
            headers={"Authorization": f"Bearer {context.token}"},
            timeout=10.0,
        )
        print(response.json())
        return False

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
