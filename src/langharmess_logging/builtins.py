"""Descriptors for CLI and server logging plugins."""

from __future__ import annotations

from langharmess_logging.contracts import SPEC_LOG
from langharmess_plugin.registry import PluginDescriptor


def log_descriptor(role: str, directory: str) -> PluginDescriptor:
    if role not in {"cli", "server"}:
        raise ValueError(f"Unsupported log role: {role}")
    return PluginDescriptor(
        name=f"{role}-log",
        version="1.0.0",
        module="langharmess_logging.plugin",
        factory="file-log-plugin-factory",
        instance=f"{role}-log",
        specification=SPEC_LOG,
        properties={
            "plugin.log.directory": directory,
            "plugin.log.name": f"langharmess.{role}",
            "plugin.log.filename": f"langharmess_{role}.log",
            "plugin.log.capture": (
                "uvicorn.error,uvicorn.access" if role == "server" else ""
            ),
        },
    )
