"""Health command plugin."""

from __future__ import annotations

import argparse

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_cli.common.api_guard import APIGuard
from langharmess_cli.contracts import (
    SPEC_CLI_COMMAND,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)


@ComponentFactory("cli-health-plugin-factory")
@Provides(SPEC_CLI_COMMAND)
@Property("_plugin_name", "plugin.name", "health-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_base_url", "plugin.base_url", "http://127.0.0.1:8000")
@Property("_token", "plugin.token", "secret")
class HealthCommandPlugin:
    def __init__(self) -> None:
        self._plugin_name = "health-command"
        self._plugin_version = "1.0.0"
        self._base_url = "http://127.0.0.1:8000"
        self._token = "secret"

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--base-url", default=self._base_url)

    def _handler(self, args: argparse.Namespace) -> int:
        base_url = args.base_url.rstrip("/")
        APIGuard(base_url).ensure_api_server()
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
                add_arguments=self._add_arguments,
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
        APIGuard(base_url).ensure_api_server()
        response = httpx.get(
            f"{base_url}/health",
            headers={"Authorization": f"Bearer {context.token}"},
            timeout=10.0,
        )
        print(response.json())
        return False

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
