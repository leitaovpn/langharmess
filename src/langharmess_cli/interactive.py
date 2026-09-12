"""Interactive command-line shell."""

from __future__ import annotations

import cmd
from collections.abc import Iterable, Mapping

import httpx

from langharmess_cli.contracts import InteractiveCommandSpec


class InteractiveCLIRunner(cmd.Cmd):
    prompt = "langharmess> "

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        commands: Iterable[InteractiveCommandSpec],
    ) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.commands: Mapping[str, InteractiveCommandSpec] = {
            command.name: command for command in commands
        }

    def do_stream(self, line: str) -> None:
        with httpx.stream(
            "POST",
            f"{self.base_url}/stream",
            json={"input": line},
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=None,
        ) as response:
            for chunk in response.iter_lines():
                print(chunk)

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
