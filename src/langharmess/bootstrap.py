"""Configuration-first assembly for UI and server process modes."""

from __future__ import annotations

import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterable
from dataclasses import replace
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import cast

from langharmess_api.common.server import _apply_agent_configs
from langharmess_api.contracts import SPEC_SERVER_SERVER, ServerServerProvider
from langharmess_cli.contracts import SPEC_UI_SERVER, UIServerProvider
from langharmess_config.contracts import SPEC_CONFIGS, Configs
from langharmess_plugin.config_store import apply_overrides, load_overrides
from langharmess_plugin.contracts import DynamicPluginManager
from langharmess_plugin.coordinator import RuntimeMutationCoordinator
from langharmess_plugin.discovery import PluginDiscovery
from langharmess_plugin.package import PluginPackage
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.state_store import SqliteRuntimeStateStore

LOGGER = logging.getLogger("langharmess.bootstrap")
CONFIG_ENTRY_POINT_GROUP = "langharmess.config"
DEFAULT_CONFIG_DIR = str(Path.home() / ".langharmess")
DEFAULT_PACKAGE_PATHS = {
    "config": "langharmess_config.plugin:builtin_package",
    "ui": "langharmess_cli.plugin:builtin_package",
    "sdk": "langharmess_api.sdk:package",
    "server": "langharmess_api.plugin:builtin_package",
    "agent": "langharmess_core.plugin:builtin_package",
    "log": "langharmess_logging.plugin:builtin_package",
}


class BootstrapError(RuntimeError):
    """Raised when configured module assembly cannot be loaded."""


def parse_options(argv: list[str]) -> tuple[Namespace, list[str]]:
    parser = ArgumentParser(description="LangHarmess")
    parser.add_argument("--mode", choices=("ui", "all", "server"), default="all")
    parser.add_argument("--server-ip", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=11534)
    parser.add_argument(
        "--config-dir",
        "--config_dir",
        "--dir",
        dest="config_dir",
        default=os.environ.get("LANG_HARMESS_DIR", DEFAULT_CONFIG_DIR),
    )
    return parser.parse_known_args(argv)


def load_package(path: str, *, config_dir: str, section: str) -> PluginPackage:
    """Load and validate one configured ``module:factory`` package path."""
    try:
        module_name, separator, attribute = path.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("expected module:attr")
        factory = getattr(import_module(module_name), attribute)
        if not callable(factory):
            raise TypeError("target is not callable")
        package = factory()
        if not isinstance(package, PluginPackage):
            raise TypeError("factory did not return PluginPackage")
        return package
    except Exception as exc:
        raise BootstrapError(
            f"Cannot load {section} from {path!r} using config-dir "
            f"{config_dir!r}: {exc}"
        ) from exc


def selected_package_paths(configs: Configs, *, mode: str) -> dict[str, str]:
    roles = ("ui", "sdk", "log") if mode in {"ui", "all"} else (
        "server",
        "agent",
        "log",
    )
    selected: dict[str, str] = {}
    for role in roles:
        section_role = "ui" if role == "sdk" else role
        section_name = f"plugins.{section_role}"
        key = "sdk_package" if role == "sdk" else "builtin_package"
        section = configs.get_section(section_name)
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            selected[role] = value
        else:
            selected[role] = DEFAULT_PACKAGE_PATHS[role]
            LOGGER.info("%s.%s is missing; using %s", section_name, key, selected[role])
    return selected


def _config_entry_points() -> Iterable[EntryPoint]:
    return entry_points(group=CONFIG_ENTRY_POINT_GROUP)


def _discover_config_package(config_dir: str) -> PluginPackage:
    discovered = list(_config_entry_points())
    if not discovered:
        return load_package(
            DEFAULT_PACKAGE_PATHS["config"],
            config_dir=config_dir,
            section="plugins.config",
        )
    entry_point = next((item for item in discovered if item.name == "config"), discovered[0])
    try:
        factory = entry_point.load()
        package = factory()
    except Exception as exc:
        raise BootstrapError(
            f"Cannot load {CONFIG_ENTRY_POINT_GROUP} entry point "
            f"{entry_point.name!r} for config-dir {config_dir!r}: {exc}"
        ) from exc
    if not isinstance(package, PluginPackage):
        raise BootstrapError(
            f"{CONFIG_ENTRY_POINT_GROUP} entry point {entry_point.name!r} "
            "did not return PluginPackage"
        )
    return package


def _configured_descriptor(
    descriptor: PluginDescriptor,
    *,
    config_dir: str,
    locale: str,
) -> PluginDescriptor:
    properties = dict(descriptor.properties)
    if descriptor.name == "config-toml":
        properties["plugin.config.path"] = str(Path(config_dir) / "langharmess.toml")
    if "plugin.log.directory" in properties:
        properties["plugin.log.directory"] = config_dir
    if descriptor.name == "api-plugins":
        properties["plugin.config_dir"] = config_dir
    path_properties = {
        "sqlite-checkpointer": ("plugin.checkpoint.path", "langharmess_checkpoints.sqlite3"),
        "session-index": ("plugin.sessions.path", "sessions.sqlite3"),
        "agent-registry": ("plugin.agents.path", "agents.json"),
    }
    if descriptor.name in path_properties:
        key, filename = path_properties[descriptor.name]
        properties[key] = str(Path(config_dir) / filename)
    if "plugin.ui.locale" in properties:
        properties["plugin.ui.locale"] = locale
    return replace(descriptor, properties=properties)


def _descriptors(
    packages: Iterable[PluginPackage],
    *,
    config_dir: str,
    locale: str,
    override_scope: str,
) -> list[PluginDescriptor]:
    overrides = load_overrides(config_dir, override_scope)
    result: list[PluginDescriptor] = []
    seen: set[str] = set()
    for package in packages:
        for contribution in package.contributions:
            descriptor = _configured_descriptor(
                contribution.descriptor, config_dir=config_dir, locale=locale
            )
            if (
                override_scope == "cli"
                and descriptor.name == "server-log"
                or override_scope == "api"
                and descriptor.name == "cli-log"
            ):
                continue
            if descriptor.name in seen:
                continue
            seen.add(descriptor.name)
            result.append(
                apply_overrides(descriptor, overrides[descriptor.name])
                if descriptor.name in overrides
                else descriptor
            )
    return result


def _select_packages(config_package: PluginPackage, options: Namespace) -> list[PluginPackage]:
    config_descriptors = _descriptors(
        [config_package],
        config_dir=options.config_dir,
        locale="en",
        override_scope="cli" if options.mode in {"ui", "all"} else "api",
    )
    manager = PluginManager(PluginRegistry(config_descriptors))
    manager.start()
    try:
        for descriptor in config_descriptors:
            manager.install_plugin(descriptor)
        configs = cast(Configs | None, manager.get_service(SPEC_CONFIGS))
        if configs is None:
            raise BootstrapError("Configuration package did not provide configs")
        paths = selected_package_paths(configs, mode=options.mode)
    finally:
        manager.stop()
    return [
        load_package(path, config_dir=options.config_dir, section=f"plugins.{role}")
        for role, path in paths.items()
    ]


def _run(options: Namespace, remainder: list[str]) -> int:
    config_package = _discover_config_package(options.config_dir)
    packages = [config_package, *_select_packages(config_package, options)]
    locale = "en"
    descriptors = _descriptors(
        packages,
        config_dir=options.config_dir,
        locale=locale,
        override_scope="cli" if options.mode in {"ui", "all"} else "api",
    )
    manager = PluginManager(PluginRegistry(descriptors))
    manager.start()
    try:
        coordinator: RuntimeMutationCoordinator | None = None
        if options.mode == "server":
            coordinator = RuntimeMutationCoordinator(
                manager,
                SqliteRuntimeStateStore(
                    Path(options.config_dir) / "runtime_state.sqlite3"
                ),
                PluginDiscovery(),
            )
            manager.register_runtime_service(DynamicPluginManager, coordinator)
        for descriptor in descriptors:
            manager.install_plugin(descriptor)
        if coordinator is not None:
            coordinator.rescan()
            coordinator.restore()
            _apply_agent_configs(manager, options.config_dir)
        if options.mode == "server":
            server_service = cast(
                ServerServerProvider | None, manager.get_service(SPEC_SERVER_SERVER)
            )
            if server_service is None:
                raise BootstrapError("Server package did not provide server.server")
            server_service.serve(options.server_ip, options.server_port)
            return 0
        ui_service = cast(UIServerProvider | None, manager.get_service(SPEC_UI_SERVER))
        if ui_service is None:
            raise BootstrapError("UI package did not provide ui.server")
        return ui_service.run(
            {
                "argv": remainder,
                "base_url": f"http://{options.server_ip}:{options.server_port}",
                "config_dir": options.config_dir,
                "descriptors": descriptors,
                "manager": manager,
            }
        )
    finally:
        manager.stop()


def main(argv: list[str] | None = None) -> int:
    options, remainder = parse_options(sys.argv[1:] if argv is None else argv)
    options.config_dir = str(Path(options.config_dir).expanduser().resolve())
    inherited = os.environ.get("LANG_HARMESS_DIR")
    os.environ["LANG_HARMESS_DIR"] = options.config_dir
    try:
        return _run(options, remainder)
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if inherited is None:
            os.environ.pop("LANG_HARMESS_DIR", None)
        else:
            os.environ["LANG_HARMESS_DIR"] = inherited
