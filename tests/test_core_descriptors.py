"""Tests for built-in core plugin descriptors."""

from __future__ import annotations

from pathlib import Path

from langharmess_core.contracts import (
    SPEC_CHECKPOINTER,
    SPEC_LLM,
    SPEC_MIDDLEWARE,
    SPEC_TOOL,
)
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
    builtin_package,
    dynamic_package,
    dynamic_template_descriptor,
    session_index_descriptor,
    sqlite_checkpointer_descriptor,
)

EXPECTED_DYNAMIC_CONTRIBUTIONS = frozenset(
    {
        "cache-plugin-template",
        "checkpointer-plugin-template",
        "context-schema-plugin-template",
        "debug-plugin-template",
        "interrupt-after-plugin-template",
        "interrupt-before-plugin-template",
        "middleware-plugin-template",
        "response-format-plugin-template",
        "state-schema-plugin-template",
        "store-plugin-template",
        "system-prompt-plugin-template",
        "tools-plugin-template",
        "transformers-plugin-template",
    }
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
        "_scoped_llm_providers": "(plugin.agent_id=a1)",
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


def test_dynamic_package_covers_plugins_absent_from_builtin() -> None:
    package = dynamic_package()
    assert package.id == "dynamic.core"
    assert package.version == "1.0.0"

    builtin = builtin_package()
    dynamic_ids = {contribution.id for contribution in package.contributions}
    assert dynamic_ids == EXPECTED_DYNAMIC_CONTRIBUTIONS
    assert dynamic_ids.isdisjoint(
        {contribution.id for contribution in builtin.contributions}
    )
    builtin_names = {
        contribution.descriptor.name for contribution in builtin.contributions
    }
    assert {
        contribution.descriptor.name for contribution in package.contributions
    }.isdisjoint(builtin_names)


def test_dynamic_templates_install_without_instantiating() -> None:
    for contribution in dynamic_package().contributions:
        descriptor = contribution.descriptor
        assert contribution.target == "agent"
        assert descriptor.name.endswith("-template")
        assert descriptor.enabled is False
        assert descriptor.instance == descriptor.name
        assert descriptor.scope == "agent"
        assert descriptor.scope_parent == "root"
        assert descriptor.module.startswith("langharmess_core.plugins.")
        assert descriptor.factory.endswith("-factory")
        assert descriptor.specification.startswith("agent.plugin.")


def test_dynamic_template_descriptor_matches_catalog_entry() -> None:
    descriptor = dynamic_template_descriptor("middleware-plugin")
    assert descriptor.module == "langharmess_core.plugins.middleware.template_middleware"
    assert descriptor.factory == "middleware-plugin-factory"
    assert descriptor.specification == SPEC_MIDDLEWARE
