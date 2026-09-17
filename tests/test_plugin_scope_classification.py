"""Every built-in plugin belongs to the canonical runtime scope tree."""

from langharmess_api.plugin import (
    api_agents_descriptor,
    api_auth_descriptor,
    api_db_descriptor,
    api_health_descriptor,
    api_plugins_descriptor,
    api_rate_limit_descriptor,
    api_server_descriptor,
    api_sessions_descriptor,
    api_stream_descriptor,
)
from langharmess_cli.plugin import cli_descriptors
from langharmess_config.plugin import config_descriptors
from langharmess_core.plugin import (
    agent_directory_descriptor,
    agent_loop_descriptor,
    agent_loop_template_descriptor,
    agent_plugin_descriptor,
    agent_plugin_template_descriptor,
    agent_registry_descriptor,
    session_index_descriptor,
    sqlite_checkpointer_descriptor,
)
from langharmess_logging.plugin import log_descriptor


def test_common_plugins_are_in_root_scope() -> None:
    descriptors = [
        *config_descriptors("/tmp/config"),
        log_descriptor("server", "/tmp/log"),
        log_descriptor("cli", "/tmp/log"),
        api_db_descriptor(),
    ]
    assert {(item.scope, item.scope_parent) for item in descriptors} == {
        ("root", None)
    }


def test_cli_plugins_are_in_ui_scope() -> None:
    assert {(item.scope, item.scope_parent) for item in cli_descriptors("en")} == {
        ("ui", "root")
    }


def test_server_plugins_and_checkpointer_are_in_server_scope() -> None:
    descriptors = [
        api_auth_descriptor(),
        api_rate_limit_descriptor(),
        api_health_descriptor(),
        api_stream_descriptor(),
        api_plugins_descriptor("/tmp/config"),
        api_sessions_descriptor(),
        api_agents_descriptor(),
        api_server_descriptor(),
        sqlite_checkpointer_descriptor("/tmp/data"),
        session_index_descriptor("/tmp/data"),
        agent_registry_descriptor("/tmp/data"),
        agent_directory_descriptor(),
    ]
    assert {(item.scope, item.scope_parent) for item in descriptors} == {
        ("server", "root")
    }


def test_agent_templates_and_instances_form_two_levels() -> None:
    templates = [
        agent_plugin_template_descriptor("llm"),
        agent_plugin_template_descriptor("tools"),
        agent_loop_template_descriptor(),
    ]
    assert {(item.scope, item.scope_parent) for item in templates} == {
        ("agent", "root")
    }

    instances = [
        agent_plugin_descriptor("alpha", "llm"),
        agent_loop_descriptor("alpha", []),
    ]
    assert {(item.scope, item.scope_parent) for item in instances} == {
        ("agent:alpha", "agent")
    }
