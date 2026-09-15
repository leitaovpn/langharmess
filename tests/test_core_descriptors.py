"""Tests for built-in core plugin descriptors."""

from __future__ import annotations

from pathlib import Path

from langharmess_core.plugin import (
    agent_registry_descriptor,
    session_index_descriptor,
    sqlite_checkpointer_descriptor,
)


def test_state_descriptors_store_files_under_directory(tmp_path: Path) -> None:
    directory = str(tmp_path)
    checkpointer = sqlite_checkpointer_descriptor(directory)
    sessions = session_index_descriptor(directory)
    registry = agent_registry_descriptor(directory)

    assert checkpointer.properties["plugin.checkpoint.path"] == str(
        tmp_path / "langharmess_checkpoints.sqlite3"
    )
    assert sessions.properties["plugin.sessions.path"] == str(
        tmp_path / "sessions.sqlite3"
    )
    assert registry.properties["plugin.agents.path"] == str(tmp_path / "agents.json")


def test_state_descriptors_declare_their_specifications(tmp_path: Path) -> None:
    directory = str(tmp_path)
    assert sqlite_checkpointer_descriptor(directory).specification == (
        "agent.plugin.checkpointer"
    )
    assert session_index_descriptor(directory).specification == "session.index"
    assert agent_registry_descriptor(directory).specification == "agent.registry"
