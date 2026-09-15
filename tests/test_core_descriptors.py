"""Tests for built-in core plugin descriptors."""

from __future__ import annotations

from pathlib import Path

from langharmess_core.contracts import SPEC_CHECKPOINTER, SPEC_LLM, SPEC_TOOL
from langharmess_core.plugin import (
    agent_directory_descriptor,
    agent_filter,
    agent_loop_descriptor,
    agent_loop_template_descriptor,
    agent_plugin_descriptor,
    agent_plugin_template_descriptor,
    agent_registry_descriptor,
    agent_required_modules,
    agent_scoped_specifications,
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


def test_agent_plugin_descriptor_is_scoped_to_the_agent() -> None:
    descriptor = agent_plugin_descriptor("a1", "tools")
    assert descriptor.instance == "tools@a1"
    assert descriptor.module == "langharmess_core.plugins.tools.workspace"
    assert descriptor.specification == SPEC_TOOL
    assert descriptor.properties == {
        "plugin.tools.root_dir": ".",
        "plugin.agent_id": "a1",
    }

    llm = agent_plugin_descriptor("a1", "llm", {"plugin.model.name": "m"})
    assert llm.properties == {"plugin.model.name": "m", "plugin.agent_id": "a1"}


def test_agent_plugin_templates_install_without_instantiating() -> None:
    for plugin in ("llm", "tools", "name"):
        template = agent_plugin_template_descriptor(plugin)
        assert template.enabled is False
        assert template.instance == f"{plugin}-template"
    assert agent_loop_template_descriptor().enabled is False


def test_agent_loop_descriptor_only_filters_scoped_specifications() -> None:
    loop = agent_loop_descriptor("a1", [SPEC_LLM, SPEC_TOOL, SPEC_CHECKPOINTER])
    assert loop.instance == "agent-loop@a1"
    assert loop.properties["plugin.agent_id"] == "a1"
    assert loop.properties["requires.filters"] == {
        "_llm_provider": "(plugin.agent_id=a1)",
        "_tool_providers": "(plugin.agent_id=a1)",
    }


def test_agent_scoped_specifications_cover_the_catalog() -> None:
    assert agent_scoped_specifications() == [SPEC_LLM, SPEC_TOOL, "agent.plugin.name"]


def test_agent_required_modules_lists_expected_bundles() -> None:
    assert agent_required_modules() == [
        "langharmess_core.plugins.tools.workspace",
        "langharmess_core.plugins.name.template_name",
        "langharmess_core.plugins.loop.agent_loop",
    ]


def test_agent_filter_builds_an_ldap_filter() -> None:
    assert agent_filter("a1") == "(plugin.agent_id=a1)"


def test_agent_directory_descriptor_declares_its_specification() -> None:
    descriptor = agent_directory_descriptor()
    assert descriptor.specification == "agent.directory"
    assert descriptor.module == "langharmess_core.plugins.agents.directory"
