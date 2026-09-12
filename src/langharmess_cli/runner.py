"""CLI runner that builds an argparse parser from command plugins."""

from __future__ import annotations

import argparse
from collections.abc import Iterable

from langharmess_cli.contracts import CommandSpec


class CLIRunner:
    def __init__(self, providers: Iterable[CommandSpec]) -> None:
        self._commands = list(providers)

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="langharmess")
        subparsers = parser.add_subparsers(dest="command", required=True)

        for command in self._commands:
            subparser = subparsers.add_parser(command.name, help=command.help)
            if command.add_arguments is not None:
                command.add_arguments(subparser)
            subparser.set_defaults(_handler=command.handler)

        return parser

    def run(self, argv: list[str]) -> int:
        parser = self.build_parser()
        namespace = parser.parse_args(argv)
        handler = namespace._handler
        return int(handler(namespace))
