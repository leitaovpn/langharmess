"""SQLite-backed checkpointer plugin for persistent agent memory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides

from langharmess_core.contracts import CheckpointerProvider


@ComponentFactory("sqlite-checkpointer-plugin-factory")
@Provides(CheckpointerProvider)
@Property("_plugin_name", "plugin.name", "sqlite-checkpointer")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_ranking", "service.ranking", 1000)
@Property("_path", "plugin.checkpoint.path", "langharmess_checkpoints.sqlite3")
class SQLiteCheckpointerPlugin:
    """Creates the async SQLite saver lazily on the API event loop."""

    def __init__(self) -> None:
        self._plugin_name = "sqlite-checkpointer"
        self._plugin_version = "1.0.0"
        self._ranking = 1000
        self._path = "langharmess_checkpoints.sqlite3"
        self._connection: aiosqlite.Connection | None = None
        self._checkpointer: AsyncSqliteSaver | None = None

    def get_checkpointer(self) -> AsyncSqliteSaver:
        if self._checkpointer is None:
            asyncio.get_running_loop()
            path = Path(self._path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = aiosqlite.connect(path)
            self._checkpointer = AsyncSqliteSaver(self._connection)
        return self._checkpointer

    @Invalidate
    def _invalidate(self, bundle_context: Any) -> None:
        if self._connection is None:
            return
        connection = self._connection
        self._connection = None
        self._checkpointer = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(connection.close())
        else:
            loop.create_task(connection.close())

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
