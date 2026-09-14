"""Command-line assembly and dispatch."""

from __future__ import annotations

import os
import random
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from langharmess_cli.common.api_guard import APIGuard
from langharmess_cli.common.i18n import get_locale
from langharmess_cli.common.interactive import InteractiveCLIRunner
from langharmess_cli.common.runner import CLIRunner
from langharmess_cli.contracts import SPEC_CLI_COMMAND, SPEC_CLI_RENDERER
from langharmess_cli.plugin import cli_descriptors
from langharmess_config.contracts import SPEC_CONFIGS
from langharmess_config.plugin import config_descriptors
from langharmess_logging.contracts import SPEC_LOG
from langharmess_logging.plugin import log_descriptor
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginRegistry


def _global_options(argv: list[str]) -> tuple[Namespace, list[str]]:
    parser = ArgumentParser(add_help=False)
    parser.add_argument("--provider")
    parser.add_argument("--dir", default=str(Path.home() / ".langharmess"))
    return parser.parse_known_args(argv)


def _locale_option(argv: list[str], *, default: str) -> str:
    """Extract the --locale flag from argv, falling back to `default`."""
    for index, arg in enumerate(argv):
        if arg == "--locale" and index + 1 < len(argv):
            return argv[index + 1].lower()
        if arg.startswith("--locale="):
            return arg.split("=", 1)[1].lower()
    return default


def main() -> int:
    options, argv = _global_options(sys.argv[1:])
    locale = _locale_option(argv, default=get_locale())
    directory = str(Path(options.dir).expanduser().resolve())
    inherited_directory = os.environ.get("LANG_HARMESS_DIR")
    os.environ["LANG_HARMESS_DIR"] = directory
    registry = PluginRegistry(
        config_descriptors(directory)
        + [log_descriptor("cli", directory)]
        + cli_descriptors(locale)
    )
    manager = PluginManager(registry)
    manager.start()
    try:
        for descriptor in registry.list():
            manager.install_plugin(descriptor)

        providers = manager.get_services(SPEC_CLI_COMMAND)
        get_service = getattr(manager, "get_service", lambda specification: None)
        configs = get_service(SPEC_CONFIGS)
        log_provider = get_service(SPEC_LOG)
        renderer = get_service(SPEC_CLI_RENDERER)
        if log_provider is not None and hasattr(log_provider, "get_logger"):
            log_provider.get_logger().info("CLI started")

        commands = [
            command for provider in providers for command in provider.get_commands()
        ]

        if not argv or argv[0] == "interactive":
            base_url = "http://127.0.0.1:8000"
            token = "secret"
            interactive_args = argv[1:] if argv and argv[0] == "interactive" else argv
            for index, arg in enumerate(interactive_args):
                if arg == "--base-url" and index + 1 < len(interactive_args):
                    base_url = interactive_args[index + 1]
                elif arg.startswith("--base-url="):
                    base_url = arg.split("=", 1)[1]
                elif arg == "--token" and index + 1 < len(interactive_args):
                    token = interactive_args[index + 1]
                elif arg.startswith("--token="):
                    token = arg.split("=", 1)[1]
            APIGuard(base_url).ensure_api_server()
            interactive_commands = [
                command
                for provider in providers
                for command in provider.get_interactive_commands()
            ]
            selected_provider = options.provider
            if configs is not None and selected_provider is None:
                provider_names = configs.list_providers()
                if provider_names:
                    selected_provider = random.choice(provider_names)
            provider_config = (
                configs.get_provider(selected_provider)
                if configs is not None and selected_provider
                else {}
            )
            if options.provider and not provider_config:
                print(f"Unknown provider: {options.provider}", file=sys.stderr)
                return 2
            interactive_runner = InteractiveCLIRunner(
                base_url=base_url,
                token=token,
                model=provider_config.get(
                    "model", os.environ.get("LANG_HARMESS_MODEL", "gpt-4o-mini")
                ),
                provider_name=selected_provider or "environment",
                model_protocol=provider_config.get("protocol", "chat"),
                api_key=provider_config.get(
                    "api_key", os.environ.get("LANG_HARMESS_API_KEY", "")
                ),
                model_base_url=provider_config.get(
                    "base_url", os.environ.get("LANG_HARMESS_BASE_URL", "")
                ),
                commands=interactive_commands,
                renderer=renderer,
                history_file=str(Path(directory) / "history"),
                locale=locale,
            )
            interactive_runner.configs = configs
            interactive_runner.log = log_provider
            interactive_runner.cmdloop()
            return 0

        cli_runner = CLIRunner(commands)
        cli_runner.configs = configs
        cli_runner.log = log_provider
        return cli_runner.run(argv)
    finally:
        manager.stop()
        if inherited_directory is None:
            os.environ.pop("LANG_HARMESS_DIR", None)
        else:
            os.environ["LANG_HARMESS_DIR"] = inherited_directory
