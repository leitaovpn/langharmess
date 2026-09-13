"""Interactive command-line shell."""

from __future__ import annotations

import cmd
import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

import httpx

from langharmess_cli.contracts import InteractiveCommandSpec


class InteractiveCLIRunner(cmd.Cmd):
    intro = """
┌──────────────────────────────────────────────┐
│                 langharmess                  │
│                                              │
│  Type a message to start a conversation.     │
│  /help shows commands · /exit leaves safely  │
└──────────────────────────────────────────────┘
""".strip()
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
    ) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model
        self.api_key = api_key
        self.model_base_url = model_base_url.rstrip("/")
        self.configs = configs
        self.log: Any = None
        self.session_id = uuid4().hex
        self.commands: Mapping[str, InteractiveCommandSpec] = {
            command.name: command for command in commands
        }

    def do_stream(self, line: str) -> None:
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
                event = json.loads(line_text)
                if event["type"] == "assistant":
                    print(event["content"], end="", flush=True)
                elif event["type"] == "tool_call":
                    print(f"\n[tool call] {event['name']} {event['args']}")
                elif event["type"] == "tool_output":
                    print(f"[tool output] {event['name']}: {event['output']}")
        print()

    def do_exit(self, line: str) -> bool:
        return True

    def do_quit(self, line: str) -> bool:
        return True

    def do_EOF(self, line: str) -> bool:
        print()
        return True

    def onecmd(self, line: str) -> bool:
        if line.startswith("/"):
            command_line = line[1:].strip()
            name, _, arguments = command_line.partition(" ")
            command = self.commands.get(name)
            if command is None:
                print(f"Unknown command: /{name}. Type /help for available commands.")
                return False
            return bool(command.handler(self, arguments.strip()))
        return bool(super().onecmd(line))

    def default(self, line: str) -> None:
        if not line.strip():
            return
        self.do_stream(line)
