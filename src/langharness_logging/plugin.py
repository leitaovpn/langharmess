"""Descriptors and assembly helpers for the built-in logging plugins."""

from __future__ import annotations

from pathlib import Path

from langharness_logging.contracts import SPEC_LOG
from langharness_plugin.package import PluginContribution, PluginPackage
from langharness_plugin.registry import PluginDescriptor


def log_descriptor(role: str, directory: str) -> PluginDescriptor:
    if role not in {"cli", "server"}:
        raise ValueError(f"Unsupported log role: {role}")
    return PluginDescriptor(
        name=f"{role}-log",
        version="1.0.0",
        module="langharness_logging.plugins.log",
        factory="file-log-plugin-factory",
        instance=f"{role}-log",
        specification=SPEC_LOG,
        scope="root",
        properties={
            "plugin.log.directory": directory,
            "plugin.log.name": f"langharness.{role}",
            "plugin.log.filename": f"langharness_{role}.log",
            "plugin.log.capture": (
                "uvicorn.error,uvicorn.access" if role == "server" else ""
            ),
        },
    )


def builtin_package() -> PluginPackage:
    """Describe the CLI and server logging plugins."""
    directory = str(Path.home() / ".langharness")
    return PluginPackage(
        id="builtin.logging",
        version="1.0.0",
        contributions=(
            PluginContribution(
                "server-log", "root", log_descriptor("server", directory)
            ),
            PluginContribution(
                "cli-log", "root", log_descriptor("cli", directory)
            ),
        ),
    )
