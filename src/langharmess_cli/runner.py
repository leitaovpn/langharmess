"""CLI runner that builds an argparse parser from command plugins."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from typing import Any

from langharmess_cli.contracts import CommandSpec


class CLIRunner:
    def __init__(self, providers: Iterable[CommandSpec], *, configs: Any = None) -> None:
        self._commands = list(providers)
        self.configs = configs

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="langharmess")
        parser.add_argument("--provider", help="LLM provider configured in langharmess.ini")
        parser.add_argument("--log", help="override the configured log file")
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
