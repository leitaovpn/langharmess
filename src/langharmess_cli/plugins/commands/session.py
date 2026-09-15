"""Interactive session and agent command plugin."""

from __future__ import annotations

from typing import Any

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_cli.common.i18n import tr
from langharmess_cli.contracts import (
    CLICommandProvider,
    CommandSpec,
    InteractiveCommandContext,
    InteractiveCommandSpec,
)


@ComponentFactory("cli-session-command-factory")
@Provides(CLICommandProvider)
@Property("_plugin_name", "plugin.name", "session-command")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_locale", "plugin.ui.locale", "en")
class SessionCommandPlugin:
    def __init__(self) -> None:
        self._plugin_name = "session-command"
        self._plugin_version = "1.0.0"
        self._locale = "en"

    def get_commands(self) -> list[CommandSpec]:
        return []

    def get_interactive_commands(self) -> list[InteractiveCommandSpec]:
        return [
            InteractiveCommandSpec(
                name="agents",
                help=tr(self._locale, "help_agents"),
                handler=self._list_agents,
            ),
            InteractiveCommandSpec(
                name="agent",
                help=tr(self._locale, "help_agent"),
                handler=self._switch_agent,
            ),
            InteractiveCommandSpec(
                name="sessions",
                help=tr(self._locale, "help_sessions"),
                handler=self._list_sessions,
            ),
            InteractiveCommandSpec(
                name="new",
                help=tr(self._locale, "help_new"),
                handler=self._start_new_session,
            ),
            InteractiveCommandSpec(
                name="whoami",
                help=tr(self._locale, "help_whoami"),
                handler=self._whoami,
            ),
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    def _get_json(
        self, context: InteractiveCommandContext, path: str, **params: Any
    ) -> dict[str, Any] | None:
        try:
            response = httpx.get(
                f"{context.base_url.rstrip('/')}{path}",
                params=params or None,
                headers={"Authorization": f"Bearer {context.token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            print(tr(self._locale, "identity_error", detail=exc))
            return None
        if not isinstance(payload, dict):
            print(tr(self._locale, "identity_error", detail="malformed response"))
            return None
        return payload

    def _fetch_agents(self, context: InteractiveCommandContext) -> list[Any] | None:
        payload = self._get_json(context, "/agents")
        if payload is None:
            return None
        return list(payload.get("agents") or [])

    def _print_agents(self, context: InteractiveCommandContext, agents: list[Any]) -> None:
        if not agents:
            print(tr(self._locale, "agents_none"))
            return
        print(tr(self._locale, "agents_header"))
        for agent in agents:
            marker = "*" if agent.get("id") == context.agent_id else " "
            suffix = (
                "" if agent.get("enabled", True) else tr(self._locale, "session_disabled")
            )
            description = agent.get("description") or ""
            print(f"{marker} {agent.get('id')} · {description} {suffix}".rstrip())

    def _list_agents(self, context: InteractiveCommandContext, line: str) -> bool:
        agents = self._fetch_agents(context)
        if agents is None:
            return False
        self._print_agents(context, agents)
        return False

    def _switch_agent(self, context: InteractiveCommandContext, line: str) -> bool:
        name = line.strip()
        if not name:
            print(tr(self._locale, "agent_current", name=context.agent_id))
            return self._list_agents(context, "")
        if name == context.agent_id:
            print(tr(self._locale, "agent_current", name=name))
            return False
        agents = self._fetch_agents(context)
        if agents is None:
            return False
        match = next((agent for agent in agents if agent.get("id") == name), None)
        if match is None or not match.get("enabled", True):
            print(tr(self._locale, "agent_unknown", name=name))
            return False
        context.agent_id = name
        context.refresh_status()
        print(tr(self._locale, "agent_switched", name=name))
        return False

    def _list_sessions(self, context: InteractiveCommandContext, line: str) -> bool:
        payload = self._get_json(context, "/sessions", user_id=context.user_id, limit=20)
        if payload is None:
            return False
        sessions = list(payload.get("sessions") or [])
        if not sessions:
            print(tr(self._locale, "sessions_none", user=context.user_id))
            return False
        print(tr(self._locale, "sessions_header", user=context.user_id))
        for session in sessions:
            marker = "*" if session.get("session_id") == context.session_id else " "
            agent = session.get("last_agent_id") or "-"
            print(
                f"{marker} {session.get('session_id')} · {session.get('turns', 0)}"
                f" · {agent} · {session.get('last_used_at', '')}"
            )
        return False

    def _start_new_session(self, context: InteractiveCommandContext, line: str) -> bool:
        context.session_id = None
        context.refresh_status()
        print(tr(self._locale, "new_session_pending"))
        return False

    def _whoami(self, context: InteractiveCommandContext, line: str) -> bool:
        session = context.session_id or tr(self._locale, "session_new")
        print(
            tr(
                self._locale,
                "whoami",
                user=context.user_id,
                agent=context.agent_id,
                session=session,
                base_url=context.base_url,
            )
        )
        return False
