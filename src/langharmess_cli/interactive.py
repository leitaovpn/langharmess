"""Interactive command-line shell."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style

from langharmess_cli.contracts import InteractiveCommandSpec, InteractiveRenderer
from langharmess_cli.i18n import tr
from langharmess_cli.plugins.rich_renderer import RichInteractiveRenderer


class InteractiveCLIRunner:
    intro = "Type a message to start a conversation.\n/help shows commands · /exit leaves safely"
    prompt = "langharmess> "

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        commands: Iterable[InteractiveCommandSpec],
        model: str = "gpt-4o-mini",
        provider_name: str = "environment",
        model_protocol: str = "chat",
        api_key: str = "",
        model_base_url: str = "",
        configs: Any = None,
        renderer: InteractiveRenderer | None = None,
        history_file: str | None = None,
        session: Any = None,
        locale: str = "en",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model
        self.provider_name = provider_name
        self.model_protocol = model_protocol
        self.api_key = api_key
        self.model_base_url = model_base_url.rstrip("/")
        self.configs = configs
        self.log: Any = None
        self.renderer = renderer or RichInteractiveRenderer()
        self.locale = locale
        if hasattr(self.renderer, "set_model"):
            self._update_model_status()
        self.session_id = uuid4().hex
        self.commands: Mapping[str, InteractiveCommandSpec] = {
            command.name: command for command in commands
        }
        self._interactive_input = sys.stdin.isatty()
        history: History = InMemoryHistory()
        if history_file:
            path = Path(history_file).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            history = FileHistory(str(path))
        self._session = session
        if self._session is None and self._interactive_input:
            self._session = PromptSession(
                history=history,
                auto_suggest=AutoSuggestFromHistory(),
                style=Style.from_dict(
                    {
                        "prompt": "bold ansicyan",
                        "bottom-toolbar": "bg:#222222 #aaaaaa",
                    }
                ),
            )

    def cmdloop(self, intro: str | None = None) -> None:
        self.renderer.show_welcome(intro or tr(self.locale, "intro"))
        if hasattr(self.renderer, "get_status_text"):
            toolbar: Any = self.renderer.get_status_text
        else:
            toolbar = f" {self.model} · {tr(self.locale, 'toolbar_hint')} "
        while True:
            try:
                line = (
                    self._session.prompt(
                        [("class:prompt", self.prompt)],
                        completer=self._command_completer(),
                        complete_style=CompleteStyle.MULTI_COLUMN,
                        bottom_toolbar=toolbar,
                    )
                    if self._interactive_input and self._session is not None
                    else input(self.prompt)
                )
            except EOFError:
                self.do_EOF("")
                return
            except KeyboardInterrupt:
                self.renderer.show_error(tr(self.locale, "cancelled"))
                continue
            if self.onecmd(line):
                return

    def _command_completer(self) -> WordCompleter:
        return WordCompleter(
            [f"/{name}" for name in sorted(self.commands)],
            meta_dict={
                f"/{name}": command.help for name, command in self.commands.items()
            },
            sentence=True,
        )

    def do_stream(self, line: str) -> None:
        self.renderer.start_response()
        payload: dict[str, Any] = {
            "input": line,
            "model": self.model,
            "protocol": self.model_protocol,
            "api_key": self.api_key,
            "base_url": self.model_base_url,
            "session_id": self.session_id,
        }
        if self._stream_usage_disabled():
            payload["stream_usage"] = False
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/stream",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=None,
            ) as response:
                response.raise_for_status()
                for line_text in response.iter_lines():
                    self.renderer.render_event(json.loads(line_text))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            self.renderer.show_error(str(exc))
        except KeyboardInterrupt:
            self.renderer.show_error(tr(self.locale, "cancelled"))
        finally:
            self.renderer.finish_response()

    @staticmethod
    def _stream_usage_disabled() -> bool:
        return os.environ.get("LANG_HARMESS_STREAM_USAGE", "").lower() in ("false", "0")

    def do_exit(self, line: str) -> bool:
        return True

    def do_quit(self, line: str) -> bool:
        return True

    def do_EOF(self, line: str) -> bool:
        self.renderer.finish_response()
        return True

    def onecmd(self, line: str) -> bool:
        command_line_value = line.strip()
        if command_line_value == "exit":
            return self.do_exit("")
        if command_line_value == "quit":
            return self.do_quit("")
        if command_line_value == "EOF":
            return self.do_EOF("")
        if command_line_value == "help" and "help" in self.commands:
            return bool(self.commands["help"].handler(self, ""))
        if line.startswith("/"):
            command_line = line[1:].strip()
            name, _, arguments = command_line.partition(" ")
            command = self.commands.get(name)
            if command is None:
                self.renderer.show_error(tr(self.locale, "unknown_command", name=name))
                return False
            return bool(command.handler(self, arguments.strip()))
        self.default(line)
        return False

    def default(self, line: str) -> None:
        if not line.strip():
            return
        self.do_stream(line)

    def list_providers(self) -> list[str]:
        if self.configs is None:
            return []
        return [str(name) for name in self.configs.list_providers()]

    def switch_provider(self, name: str) -> bool:
        if self.configs is None:
            self.renderer.show_error(tr(self.locale, "model_unknown", name=name))
            return False
        try:
            provider = self.configs.get_provider(name)
        except ValueError as exc:
            self.renderer.show_error(str(exc))
            return False
        if not provider:
            self.renderer.show_error(tr(self.locale, "model_unknown", name=name))
            return False
        provider_changed = name != self.provider_name
        self.provider_name = name
        self.model = str(provider["model"])
        self.model_protocol = str(provider.get("protocol", "chat"))
        self.api_key = str(provider.get("api_key", ""))
        self.model_base_url = str(provider.get("base_url", "")).rstrip("/")
        if provider_changed:
            self.session_id = uuid4().hex
        self._update_model_status()
        print(
            tr(
                self.locale,
                "model_switched",
                name=name,
                model=self.model,
                protocol=self.model_protocol,
            )
        )
        return True

    def _update_model_status(self) -> None:
        self.renderer.set_model(
            f"{self.provider_name} · {self.model} · {self.model_protocol}"
        )
