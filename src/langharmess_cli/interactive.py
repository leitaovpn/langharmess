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
        path = line.strip() or "/health"
        if not path.startswith("/"):
            path = f"/{path}"
        response = httpx.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=10.0,
        )
        if response.status_code == 200:
            print(response.json())
        else:
            print(response.text)

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

    def default(self, line: str) -> None:
        if not line.strip():
            return
        if line.startswith("/"):
            self.do_call(line[1:])
        else:
            self.do_stream(line)
