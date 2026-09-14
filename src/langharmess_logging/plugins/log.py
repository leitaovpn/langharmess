"""File-backed logging plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pelix.ipopo.decorators import (
    ComponentFactory,
    Invalidate,
    Property,
    Provides,
    Validate,
)

from langharmess_logging.contracts import LogProvider


@ComponentFactory("file-log-plugin-factory")
@Provides(LogProvider)
@Property("_directory", "plugin.log.directory", "~/.langharmess")
@Property("_logger_name", "plugin.log.name", "langharmess")
@Property("_filename", "plugin.log.filename", "langharmess.log")
@Property("_captured_logger_names", "plugin.log.capture", "")
class FileLogPlugin:
    def __init__(self) -> None:
        self._directory = "~/.langharmess"
        self._logger_name = "langharmess"
        self._filename = "langharmess.log"
        self._captured_logger_names = ""
        self._logger = logging.getLogger(self._logger_name)
        self._handler: logging.FileHandler | None = None
        self._attached_loggers: list[logging.Logger] = []

    @Validate
    def validate(self, bundle_context: Any) -> None:
        directory = Path(self._directory).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(self._logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = logging.FileHandler(
            directory / self._filename, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        self._logger.addHandler(handler)
        self._attached_loggers = [self._logger]
        for name in self._captured_logger_names.split(","):
            if not name.strip():
                continue
            captured_logger = logging.getLogger(name.strip())
            for existing in captured_logger.handlers[:]:
                captured_logger.removeHandler(existing)
                existing.close()
            captured_logger.setLevel(logging.INFO)
            captured_logger.propagate = False
            captured_logger.addHandler(handler)
            self._attached_loggers.append(captured_logger)
        self._handler = handler

    @Invalidate
    def invalidate(self, bundle_context: Any) -> None:
        if self._handler is not None:
            for logger in self._attached_loggers:
                logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None
            self._attached_loggers = []

    def get_logger(self) -> logging.Logger:
        return self._logger
