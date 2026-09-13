"""Configuration plugin tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langharmess_config.builtins import config_descriptors
from langharmess_config.contracts import SPEC_CONFIGS
from langharmess_config.plugins.configs import ConfigsPlugin
from langharmess_config.plugins.toml import TOMLConfigPlugin
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginRegistry


def test_toml_config_plugin_creates_and_reads_user_config(tmp_path: Path) -> None:
    path = tmp_path / ".langharmess" / "langharmess.toml"
    plugin = TOMLConfigPlugin()
    plugin._config_path = str(path)

    config = plugin.get_config()

    assert path.is_file()
    assert config["DEFAULT"] == {}
    assert config["providers"]["deepseek-v4-flash"] == {
        "base_url": "xxxxx",
        "model": "xxxxx",
        "api_key": "xxxx",
    }


def test_toml_config_plugin_reads_toml_strings(tmp_path: Path) -> None:
    path = tmp_path / "langharmess.toml"
    path.write_text(
        "[providers.demo]\n"
        'base_url = "https://example.test/v1"\n'
        'model = "demo"\n',
        encoding="utf-8",
    )
    plugin = TOMLConfigPlugin()
    plugin._config_path = str(path)

    config = plugin.get_config()

    assert config["providers"]["demo"] == {
        "base_url": "https://example.test/v1",
        "model": "demo",
    }


def test_configs_plugin_merges_registered_config_plugins() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(get_config=lambda: {"DEFAULT": {"color": "blue"}}),
        SimpleNamespace(
            get_config=lambda: {
                "DEFAULT": {"color": "green"},
                "providers": {
                    "demo": {
                        "model": "demo-model",
                        "api_key": "key",
                        "base_url": "https://example.test/v1",
                    }
                },
            }
        ),
    ]

    assert configs.get("DEFAULT", "color") == "green"
    assert configs.get("DEFAULT", "missing", "fallback") == "fallback"
    assert configs.get_section("providers.demo")["model"] == "demo-model"
    assert configs.get_provider("demo")["api_key"] == "key"
    assert configs.list_providers() == ["demo"]


def test_configs_get_returns_fallback_for_non_string_toml_values() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(get_config=lambda: {"runtime": {"retries": 3}})
    ]

    assert configs.get("runtime", "retries", "fallback") == "fallback"


def test_configs_service_aggregates_toml_plugin_in_ipopo(tmp_path: Path) -> None:
    manager = PluginManager(PluginRegistry(config_descriptors(str(tmp_path))))
    manager.start()
    try:
        for descriptor in manager.registry.list():
            manager.install_plugin(descriptor)
        configs = manager.get_service(SPEC_CONFIGS)
        assert configs is not None
        assert configs.get_provider("deepseek-v4-flash")["model"] == "xxxxx"
    finally:
        manager.stop()
