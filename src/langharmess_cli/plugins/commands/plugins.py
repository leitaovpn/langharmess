"""Interactive plugin-configuration command plugin."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)

DEFAULT_SCOPE = "api"


def _coerce(value: str) -> Any:
    """Typed values when the text looks like JSON: 5 stays an int, abc a str."""
    try:
        return json.loads(value)
    except ValueError:
        return value


@ComponentFactory("cli-plugins-command-factory")
@Provides(CLICommandProvider)
@Property("_plugin_name", "plugin.name", "plugin-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_locale", "plugin.ui.locale", "en")
class PluginCommandPlugin:
    """Reads and edits versioned plugin configuration through the API."""

    def __init__(self) -> None:
        self._plugin_name = "plugin-command"
        self._plugin_version = "1.0.0"
        self._locale = "en"

    def get_commands(self) -> list[CommandSpec]:
        return []

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="plugins",
                help=(
                    "Plugin configuration: list|set|enable|disable|history|rollback "
                    "[scope] (scope: api, cli, or agent:<id>)"
                ),
                handler=self._handle,
            )
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def _handle(self, context: InteractiveCommandContext, line: str) -> bool:
        words = line.split()
        if not words:
            self._usage()
            return False
        action, arguments = words[0].lower(), words[1:]
        try:
            if action == "list":
                self._list(context, arguments)
            elif action in ("set", "enable", "disable"):
                self._update(context, action, arguments)
            elif action == "history":
                self._history(context, arguments)
            elif action == "rollback":
                self._rollback(context, arguments)
            else:
                print(f"Unknown /plugins action: {action}")
                self._usage()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Plugin request failed: {exc}")
        return False

    def _usage(self) -> None:
        print(
            "usage: /plugins list|history|rollback [scope] [version]"
            " | /plugins set|enable|disable [scope] <plugin> [KEY=VALUE]"
        )

    def _list(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        scope = self._scope(arguments, index=0)
        payload = self._get(context, "/plugins", scope=scope)
        print(f"scope {scope} · version {payload.get('version')}")
        plugins = payload.get("plugins") or {}
        if not plugins:
            print("no plugin overrides")
            return
        for name in sorted(plugins):
            entry = plugins[name] or {}
            properties = entry.get("properties") or {}
            pairs = " ".join(
                f"{key}={value}" for key, value in sorted(properties.items())
            )
            state = "enabled" if entry.get("enabled", True) else "disabled"
            print(f"  {name} · {state} · {pairs}".rstrip())

    def _update(
        self, context: InteractiveCommandContext, action: str, arguments: list[str]
    ) -> None:
        scope, plugin, rest = self._plugin_arguments(arguments)
        if plugin is None:
            self._usage()
            return
        updates: list[tuple[str, str]] = []
        if action == "set":
            if not rest:
                self._usage()
                return
            for pair in rest:
                key, separator, value = pair.partition("=")
                if not separator or not key:
                    print(f"Expected KEY=VALUE, got: {pair}")
                    return
                updates.append((key, _coerce(value)))
        current = self._get(context, "/plugins", scope=scope)
        plugins = dict(current.get("plugins") or {})
        entry = dict(plugins.get(plugin) or {})
        properties = dict(entry.get("properties") or {})
        properties.update(updates)
        if action != "set":
            entry["enabled"] = action == "enable"
        entry["properties"] = properties
        entry.setdefault("enabled", True)
        plugins[plugin] = entry
        self._apply(
            self._put(context, "/plugins", {"plugins": plugins}, scope=scope)
        )

    def _history(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        scope = self._scope(arguments, index=0)
        payload = self._get(context, "/plugins/history", scope=scope)
        for entry in payload.get("history") or []:
            target = (
                f" · target {entry['target_seq']}" if entry.get("target_seq") else ""
            )
            print(f"  {entry.get('seq')} {entry.get('action')} {entry.get('actor')}{target}")

    def _rollback(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if not arguments:
            self._usage()
            return
        scope = DEFAULT_SCOPE
        version_text = arguments[0]
        if len(arguments) > 1:
            scope, version_text = arguments[0], arguments[1]
        if not self._is_scope(scope):
            scope = DEFAULT_SCOPE
        try:
            version = int(version_text)
        except ValueError:
            self._usage()
            return
        payload = self._post(
            context, "/plugins/rollback", {"seq": version, "actor": "cli"}, scope=scope
        )
        self._apply(payload)

    def _apply(self, payload: dict[str, Any]) -> None:
        applied = ", ".join(payload.get("applied") or []) or "-"
        restart = ", ".join(payload.get("restart_required") or []) or "-"
        print(f"version {payload.get('version')} · applied: {applied}")
        if payload.get("restart_required"):
            print(f"restart required: {restart}")

    def _scope(self, arguments: list[str], *, index: int) -> str:
        if len(arguments) > index and arguments[index]:
            return arguments[index]
        return DEFAULT_SCOPE

    def _plugin_arguments(
        self, arguments: list[str]
    ) -> tuple[str, str | None, list[str]]:
        if not arguments:
            return DEFAULT_SCOPE, None, []
        if self._is_scope(arguments[0]):
            if len(arguments) < 2:
                return arguments[0], None, []
            return arguments[0], arguments[1], arguments[2:]
        return DEFAULT_SCOPE, arguments[0], arguments[1:]

    @staticmethod
    def _is_scope(value: str) -> bool:
        return value in ("api", "cli") or value.startswith("agent:")

    def _headers(self, context: InteractiveCommandContext) -> dict[str, str]:
        return {"Authorization": f"Bearer {context.token}"}

    def _get(
        self, context: InteractiveCommandContext, path: str, *, scope: str
    ) -> dict[str, Any]:
        response = httpx.get(
            f"{context.base_url.rstrip('/')}{path}",
            params={"scope": scope},
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _put(
        self,
        context: InteractiveCommandContext,
        path: str,
        body: dict[str, Any],
        *,
        scope: str,
    ) -> dict[str, Any]:
        response = httpx.put(
            f"{context.base_url.rstrip('/')}{path}",
            params={"scope": scope},
            json={**body, "actor": "cli"},
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _post(
        self,
        context: InteractiveCommandContext,
        path: str,
        body: dict[str, Any],
        *,
        scope: str,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{context.base_url.rstrip('/')}{path}",
            params={"scope": scope},
            json={**body, "actor": "cli"},
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())
