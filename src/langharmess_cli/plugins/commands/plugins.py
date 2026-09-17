"""Interactive plugin-configuration command plugin."""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from types import SimpleNamespace
from typing import Any

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides
from rich.console import Console
from rich.table import Table

from langharmess_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)

DEFAULT_CONFIG_SCOPE = "api"
DEFAULT_RUNTIME_SCOPE = "server"


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
@Property("_base_url", "plugin.base_url", "http://127.0.0.1:11534")
class PluginCommandPlugin:
    """Reads and edits versioned plugin configuration through the API."""

    def __init__(self) -> None:
        self._plugin_name = "plugin-command"
        self._plugin_version = "1.0.0"
        self._locale = "en"
        self._base_url = "http://127.0.0.1:11534"

    def get_commands(self) -> list[CommandSpec]:
        return [
            CommandSpec(
                name="plugins",
                help="Discover and manage runtime plugins",
                handler=self._command_handler,
                add_arguments=self._add_arguments,
            )
        ]

    @staticmethod
    def _add_arguments(parser: ArgumentParser) -> None:
        parser.add_argument(
            "action",
            choices=(
                "discover",
                "list",
                "runtime",
                "config",
                "install",
                "enable",
                "disable",
                "upgrade",
                "uninstall",
            ),
        )
        parser.add_argument("values", nargs="*")
        parser.add_argument("--scope")
        parser.add_argument("--token", default="secret")

    def _command_handler(self, args: Namespace) -> int:
        context = SimpleNamespace(base_url=self._base_url, token=args.token)
        try:
            if args.action == "discover":
                self._post_raw(context, "/plugins/rescan", {})
                payload = self._get_raw(context, "/plugins/discovered")
            elif args.action == "list":
                params = {"scope": args.scope} if args.scope else None
                payload = self._get_raw(context, "/plugins/runtime", params=params)
            elif args.action == "config":
                payload = self._get_raw(
                    context,
                    "/plugins",
                    params={"scope": args.scope or DEFAULT_CONFIG_SCOPE},
                )
            elif args.action == "runtime":
                if len(args.values) < 3 or args.values[0] != "set":
                    raise ValueError("runtime requires set PLUGIN_NAME KEY=VALUE")
                properties = self._properties(args.values[2:])
                payload = self._put_raw(
                    context,
                    f"/plugins/runtime/{args.values[1]}/properties",
                    {"properties": properties},
                )
            elif args.action == "install":
                if len(args.values) != 2:
                    raise ValueError("install requires PACKAGE_ID CONTRIBUTION_ID")
                payload = self._post_raw(
                    context,
                    "/plugins/install",
                    {
                        "package_id": args.values[0],
                        "contribution_id": args.values[1],
                        "scope_id": args.scope,
                    },
                )
            elif args.action in {"enable", "disable"}:
                if len(args.values) != 1:
                    raise ValueError(f"{args.action} requires PLUGIN_NAME")
                payload = self._put_raw(
                    context,
                    f"/plugins/runtime/{args.values[0]}/enabled",
                    {"enabled": args.action == "enable"},
                )
            elif args.action == "upgrade":
                if len(args.values) != 1:
                    raise ValueError("upgrade requires PLUGIN_NAME")
                payload = self._post_raw(
                    context, f"/plugins/runtime/{args.values[0]}/upgrade", {}
                )
            else:
                if len(args.values) != 1:
                    raise ValueError("uninstall requires PLUGIN_NAME")
                payload = self._delete_raw(
                    context, f"/plugins/runtime/{args.values[0]}"
                )
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Plugin request failed: {self._error_message(exc)}")
            return 1
        self._render_noninteractive_result(args.action, args.scope, payload)
        return 0

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="plugins",
                help=(
                    "Plugin management: discover|list|runtime|config|install|uninstall|"
                    "set|enable|disable|history|rollback "
                    "[scope]; list accepts runtime scopes such as server, ui, agent, or agent:<id>"
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
            elif action == "config":
                self._config(context, arguments)
            elif action == "runtime":
                self._runtime(context, arguments)
            elif action == "discover":
                self._discover(context)
            elif action == "install":
                self._install(context, arguments)
            elif action == "uninstall":
                self._uninstall(context, arguments)
            elif action == "set":
                self._update(context, action, arguments)
            elif action in ("enable", "disable"):
                self._set_runtime_enabled(context, action, arguments)
            elif action == "history":
                self._history(context, arguments)
            elif action == "rollback":
                self._rollback(context, arguments)
            else:
                print(f"Unknown /plugins action: {action}")
                self._usage()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Plugin request failed: {self._error_message(exc)}")
        return False

    def _usage(self) -> None:
        print(
            "usage: /plugins discover"
            " | /plugins list [runtime_scope]"
            " | /plugins runtime set <plugin> KEY=VALUE [KEY=VALUE ...]"
            " | /plugins config [config_scope]"
            " | /plugins config enable|disable [config_scope] <plugin>"
            " | /plugins history|rollback [config_scope] [version]"
            " | /plugins install <package_id> <contribution_id> [scope_id]"
            " | /plugins uninstall <plugin_name>"
            " | /plugins set|enable|disable [scope] <plugin> [KEY=VALUE]"
        )

    def _list(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        scope = self._runtime_scope(arguments)
        payload = self._get(context, "/plugins/runtime", scope=scope)
        plugins = payload.get("plugins") or []
        if not plugins:
            print(f"runtime scope {scope}: no registered plugins")
            return
        self._runtime_table(scope, plugins)

    def _config(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        """Render persisted configuration overrides, distinct from runtime state."""
        if arguments and arguments[0] in {"enable", "disable"}:
            self._update(context, arguments[0], arguments[1:])
            return
        scope = self._scope(arguments, index=0)
        payload = self._get(context, "/plugins", scope=scope)
        plugins = payload.get("plugins") or {}
        if not plugins:
            print(f"configuration scope {scope}: no plugin overrides")
            return
        self._config_table(scope, payload)

    def _runtime(self, context: InteractiveCommandContext, arguments: list[str]) -> None:
        """Update properties of an installed runtime plugin instance."""
        if len(arguments) < 3 or arguments[0] != "set":
            self._usage()
            return
        name = arguments[1]
        properties: dict[str, Any] = {}
        for pair in arguments[2:]:
            key, separator, value = pair.partition("=")
            if not separator or not key:
                print(f"Expected KEY=VALUE, got: {pair}")
                return
            properties[key] = _coerce(value)
        payload = self._put_raw(
            context,
            f"/plugins/runtime/{name}/properties",
            {"properties": properties},
        )
        self._registration_table("Runtime plugin properties updated", payload)

    def _discover(self, context: InteractiveCommandContext) -> None:
        self._post_raw(context, "/plugins/rescan", {})
        payload = self._get_raw(context, "/plugins/discovered")
        packages = payload.get("packages") or []
        if not packages:
            print("no discovered plugins")
            return
        rows = [
            (
                package.get("id", "-"),
                package.get("version", "-"),
                package.get("source", "external"),
                contribution.get("id", "-"),
                contribution.get("name", "-"),
                contribution.get("specification", "-"),
                contribution.get("module", "-"),
            )
            for package in packages
            for contribution in package.get("contributions") or [{}]
        ]
        self._table(
            "Discovered plugins",
            ("Package", "Version", "Source", "Contribution", "Name", "Spec", "Module"),
            rows,
        )

    def _install(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if len(arguments) < 2:
            self._usage()
            return
        package_id, contribution_id = arguments[0], arguments[1]
        scope_id = arguments[2] if len(arguments) > 2 else None
        payload = self._post_raw(
            context,
            "/plugins/install",
            {
                "package_id": package_id,
                "contribution_id": contribution_id,
                "scope_id": scope_id,
            },
        )
        self._registration_table("Installed plugin", payload)

    def _set_runtime_enabled(
        self, context: InteractiveCommandContext, action: str, arguments: list[str]
    ) -> None:
        if len(arguments) != 1:
            self._usage()
            return
        name = arguments[0]
        payload = self._put_raw(
            context,
            f"/plugins/runtime/{name}/enabled",
            {"enabled": action == "enable"},
        )
        self._registration_table("Runtime plugin updated", payload)

    def _uninstall(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if len(arguments) != 1:
            self._usage()
            return
        payload = self._delete_raw(
            context, f"/plugins/runtime/{arguments[0]}"
        )
        self._table("Plugin removal", ("Plugin", "Removed"), ((arguments[0], payload.get("removed", False)),))

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
        self._table(
            f"Configuration history · {scope}",
            ("Version", "Action", "Actor", "Target version"),
            (
                (entry.get("seq"), entry.get("action"), entry.get("actor"), entry.get("target_seq", "-"))
                for entry in payload.get("history") or []
            ),
        )

    def _rollback(
        self, context: InteractiveCommandContext, arguments: list[str]
    ) -> None:
        if not arguments:
            self._usage()
            return
        scope = DEFAULT_CONFIG_SCOPE
        version_text = arguments[0]
        if len(arguments) > 1:
            scope, version_text = arguments[0], arguments[1]
        if not self._is_scope(scope):
            scope = DEFAULT_CONFIG_SCOPE
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
        self._table(
            "Plugin configuration applied",
            ("Version", "Applied", "Restart required"),
            ((payload.get("version"), applied, restart),),
        )

    @staticmethod
    def _table(
        title: str, columns: tuple[str, ...], rows: Any
    ) -> None:
        table = Table(title=title, header_style="bold cyan")
        for column in columns:
            table.add_column(column, overflow="fold")
        for row in rows:
            table.add_row(*(str(value) for value in row))
        Console().print(table)

    def _runtime_table(self, scope: str, plugins: list[dict[str, Any]]) -> None:
        self._table(
            f"Runtime plugins · scope {scope}",
            ("Name", "State", "Status", "Package / contribution", "Specification"),
            (
                (
                    entry.get("name", "-"),
                    "enabled" if entry.get("enabled", True) else "disabled",
                    entry.get("status", "-"),
                    f"{entry.get('package_id', '-')}/{entry.get('contribution_id', '-')}",
                    entry.get("specification", "-"),
                )
                for entry in sorted(plugins, key=lambda item: str(item.get("name", "")))
            ),
        )

    def _config_table(self, scope: str, payload: dict[str, Any]) -> None:
        plugins = payload.get("plugins") or {}
        self._table(
            f"Configuration overrides · scope {scope} · version {payload.get('version')}",
            ("Plugin", "State", "Properties"),
            (
                (
                    name,
                    "enabled" if entry.get("enabled", True) else "disabled",
                    " ".join(
                        f"{key}={value}"
                        for key, value in sorted((entry.get("properties") or {}).items())
                    )
                    or "-",
                )
                for name, entry in sorted(plugins.items())
            ),
        )

    def _registration_table(self, title: str, payload: dict[str, Any]) -> None:
        self._table(
            title,
            ("Name", "Scope", "State", "Status", "Specification"),
            ((
                payload.get("name", "-"),
                payload.get("scope_id", "-"),
                "enabled" if payload.get("enabled", True) else "disabled",
                payload.get("status", "-"),
                payload.get("specification", "-"),
            ),),
        )

    def _render_noninteractive_result(
        self, action: str, scope: str | None, payload: dict[str, Any]
    ) -> None:
        if action == "list":
            plugins = payload.get("plugins") or []
            if plugins:
                self._runtime_table(scope or "all", plugins)
            else:
                print(f"runtime scope {scope or 'all'}: no registered plugins")
        elif action == "config":
            self._config_table(scope or DEFAULT_CONFIG_SCOPE, payload)
        elif action == "discover":
            self._table("Discovered plugins", ("Package",), ((item.get("id", "-"),) for item in payload.get("packages") or []))
        else:
            self._registration_table("Plugin result", payload)

    @staticmethod
    def _properties(pairs: list[str]) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        for pair in pairs:
            key, separator, value = pair.partition("=")
            if not separator or not key:
                raise ValueError(f"Expected KEY=VALUE, got: {pair}")
            properties[key] = _coerce(value)
        return properties

    def _scope(self, arguments: list[str], *, index: int) -> str:
        if len(arguments) > index and arguments[index]:
            return arguments[index]
        return DEFAULT_CONFIG_SCOPE

    @staticmethod
    def _runtime_scope(arguments: list[str]) -> str:
        if arguments and arguments[0]:
            return arguments[0]
        return DEFAULT_RUNTIME_SCOPE

    def _plugin_arguments(
        self, arguments: list[str]
    ) -> tuple[str, str | None, list[str]]:
        if not arguments:
            return DEFAULT_CONFIG_SCOPE, None, []
        if self._is_scope(arguments[0]):
            if len(arguments) < 2:
                return arguments[0], None, []
            return arguments[0], arguments[1], arguments[2:]
        return DEFAULT_CONFIG_SCOPE, arguments[0], arguments[1:]

    @staticmethod
    def _is_scope(value: str) -> bool:
        return value in ("api", "cli") or value.startswith("agent:")

    @staticmethod
    def _error_message(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                return str(exc)
            if isinstance(detail, str):
                return detail
            if isinstance(detail, dict):
                message = detail.get("message")
                return str(message) if message else str(detail)
            return str(detail)
        return str(exc)

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

    def _get_raw(
        self,
        context: Any,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = httpx.get(
            f"{context.base_url.rstrip('/')}{path}",
            params=params,
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _post_raw(
        self, context: Any, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{context.base_url.rstrip('/')}{path}",
            json=body,
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _put_raw(
        self, context: Any, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        response = httpx.put(
            f"{context.base_url.rstrip('/')}{path}",
            json=body,
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _delete_raw(self, context: Any, path: str) -> dict[str, Any]:
        response = httpx.delete(
            f"{context.base_url.rstrip('/')}{path}",
            headers=self._headers(context),
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())
