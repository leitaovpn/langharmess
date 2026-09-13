"""Interactive command-line shell."""

from __future__ import annotations

import json
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
        api_key: str = "",
        model_base_url: str = "",
        configs: Any = None,
        renderer: InteractiveRenderer | None = None,
        history_file: str | None = None,
        session: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model
        self.api_key = api_key
        self.model_base_url = model_base_url.rstrip("/")
        self.configs = configs
        self.log: Any = None
        self.renderer = renderer or RichInteractiveRenderer()
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
        self.renderer.show_welcome(intro or self.intro)
        while True:
            try:
                line = (
                    self._session.prompt(
                        [("class:prompt", self.prompt)],
                        completer=self._command_completer(),
                        complete_style=CompleteStyle.MULTI_COLUMN,
                        bottom_toolbar=f" {self.model} · /help for commands ",
                    )
                    if self._interactive_input and self._session is not None
                    else input(self.prompt)
                )
            except EOFError:
                self.do_EOF("")
                return
            except KeyboardInterrupt:
                self.renderer.show_error("Cancelled")
                continue
            if self.onecmd(line):
                return

    def _command_completer(self) -> WordCompleter:
        return WordCompleter(
            [f"/{name}" for name in sorted(self.commands)],
            meta_dict={
                f"/{name}": command.help
                for name, command in self.commands.items()
            },
            sentence=True,
        )

    def do_stream(self, line: str) -> None:
        self.renderer.start_response()
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/stream",
                json={
                    "input": line,
                    "model": self.model,
                    "api_key": self.api_key,
                    "base_url": self.model_base_url,
                    "session_id": self.session_id,
                },
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=None,
            ) as response:
                response.raise_for_status()
                for line_text in response.iter_lines():
                    self.renderer.render_event(json.loads(line_text))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            self.renderer.show_error(str(exc))
        except KeyboardInterrupt:
            self.renderer.show_error("Cancelled")
        finally:
            self.renderer.finish_response()

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
                self.renderer.show_error(
                    f"Unknown command: /{name}. Type /help for available commands."
                )
                return False
            return bool(command.handler(self, arguments.strip()))
        self.default(line)
        return False

    def default(self, line: str) -> None:
        if not line.strip():
            return
        self.do_stream(line)
