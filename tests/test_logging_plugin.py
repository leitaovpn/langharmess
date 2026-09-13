"""Logging plugin tests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from langharmess_logging.contracts import LogProvider
from langharmess_logging.plugin import FileLogPlugin


def test_file_log_plugin_writes_to_its_configured_directory(tmp_path: Path) -> None:
    plugin = FileLogPlugin()
    plugin._directory = str(tmp_path)
    plugin._logger_name = "langharmess.test.cli"
    plugin._filename = "langharmess_cli.log"

    plugin.validate(cast(Any, None))
    try:
        assert isinstance(plugin, LogProvider)
        plugin.get_logger().info("cli started")
        for handler in plugin.get_logger().handlers:
            handler.flush()
        assert "cli started" in (tmp_path / "langharmess_cli.log").read_text()
    finally:
        plugin.invalidate(cast(Any, None))


def test_cli_and_server_plugins_use_separate_files(tmp_path: Path) -> None:
    plugins = []
    for role, filename in (
        ("cli", "langharmess_cli.log"),
        ("server", "langharmess_server.log"),
    ):
        plugin = FileLogPlugin()
        plugin._directory = str(tmp_path)
        plugin._logger_name = f"langharmess.{role}"
        plugin._filename = filename
        plugin.validate(cast(Any, None))
        plugin.get_logger().warning(role)
        plugins.append(plugin)

    try:
        assert "cli" in (tmp_path / "langharmess_cli.log").read_text()
        assert "server" not in (tmp_path / "langharmess_cli.log").read_text()
        assert "server" in (tmp_path / "langharmess_server.log").read_text()
        assert "cli" not in (tmp_path / "langharmess_server.log").read_text()
    finally:
        for plugin in plugins:
            plugin.invalidate(cast(Any, None))


def test_server_log_plugin_replaces_uvicorn_console_handlers(
    tmp_path: Path,
) -> None:
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_access = logging.getLogger("uvicorn.access")
    console = logging.StreamHandler()
    uvicorn_error.handlers = [console]
    uvicorn_access.handlers = [console]

    plugin = FileLogPlugin()
    plugin._directory = str(tmp_path)
    plugin._logger_name = "langharmess.server"
    plugin._filename = "langharmess_server.log"
    plugin._captured_logger_names = "uvicorn.error,uvicorn.access"
    plugin.validate(cast(Any, None))
    try:
        assert console not in uvicorn_error.handlers
        assert console not in uvicorn_access.handlers
        assert uvicorn_error.propagate is False
        assert uvicorn_access.propagate is False
        uvicorn_error.info("server started")
        uvicorn_access.info("GET /health")
        for handler in uvicorn_error.handlers:
            handler.flush()
        content = (tmp_path / "langharmess_server.log").read_text()
        assert "server started" in content
        assert "GET /health" in content
    finally:
        plugin.invalidate(cast(Any, None))
