"""Scope tree command plugin."""

from __future__ import annotations

import json
from argparse import Namespace
from typing import Any

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)
from langharmess_scope.render import render_scope_tree


@ComponentFactory("cli-scope-command-factory")
@Provides(CLICommandProvider)
@Property("_plugin_name", "plugin.name", "scope-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_base_url", "plugin.base_url", "http://127.0.0.1:11534")
@Property("_token", "plugin.token", "secret")
class ScopeCommandPlugin:
    """Shows the runtime scope tree served by the API."""

    def __init__(self) -> None:
        self._plugin_name = "scope-command"
        self._plugin_version = "1.0.0"
        self._base_url = "http://127.0.0.1:11534"
        self._token = "secret"

    def get_commands(self) -> list[CommandSpec]:
        return [
            CommandSpec(
                name="scope",
                help="Show the runtime scope tree",
                handler=self._handler,
            )
        ]

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="scope",
                help="Show the runtime scope tree",
                handler=self._interactive_handler,
            )
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def _handler(self, args: Namespace) -> int:
        try:
            payload = self._get(
                f"{self._base_url.rstrip('/')}/scope", self._token
            )
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Scope request failed: {exc}")
            return 1
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    def _interactive_handler(
        self, context: InteractiveCommandContext, line: str
    ) -> bool:
        try:
            payload = self._get(
                f"{context.base_url.rstrip('/')}/scope", context.token
            )
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Scope request failed: {exc}")
            return False
        print(render_scope_tree(payload.get("scopes") or []))
        return False

    @staticmethod
    def _get(base_url: str, token: str) -> dict[str, Any]:
        response = httpx.get(
            base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

