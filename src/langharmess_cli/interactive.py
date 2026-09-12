"""Interactive command-line shell."""

from __future__ import annotations

import cmd
from collections.abc import Iterable

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
        self.commands = {command.name: command for command in commands}

    def do_call(self, line: str) -> None:
        path = line.strip().split()[0] if line.strip() else "/health"
        response = httpx.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=10.0,
        )
        print(response.json())

    def do_exit(self, line: str) -> bool:
        return True

    def do_quit(self, line: str) -> bool:
        return True

    def do_EOF(self, line: str) -> bool:
        print()
        return True

    def default(self, line: str) -> None:
        if not line.strip():
            return
        name, _, args = line.partition(" ")
        command = self.commands.get(name)
        if command is None:
            print(f"Unknown command: {name}")
            return
        command.handler(args)
