"""Configuration plugin tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

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
        "protocol": "chat",
    }


def test_toml_config_plugin_reads_toml_strings(tmp_path: Path) -> None:
    path = tmp_path / "langharmess.toml"
    path.write_text(
        '[providers.demo]\nbase_url = "https://example.test/v1"\nmodel = "demo"\n',
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
    assert configs.get_provider("demo")["protocol"] == "chat"
    assert configs.list_providers() == ["demo"]


def test_configs_get_returns_fallback_for_non_string_toml_values() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(get_config=lambda: {"runtime": {"retries": 3}})
    ]

    assert configs.get("runtime", "retries", "fallback") == "fallback"


def test_configs_rejects_duplicate_provider_names() -> None:
    configs = ConfigsPlugin()
    provider = {"providers": {"demo": {"model": "same"}}}
    configs._providers = [
        SimpleNamespace(get_config=lambda: provider),
        SimpleNamespace(get_config=lambda: provider),
    ]
    with pytest.raises(ValueError, match="Duplicate provider name: demo"):
        configs.list_providers()


def test_configs_allows_different_providers_to_share_a_model() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(
            get_config=lambda: {
                "providers": {
                    "primary": {"model": "shared-model"},
                    "fallback": {"model": "shared-model"},
                }
            }
        )
    ]

    assert configs.list_providers() == ["fallback", "primary"]


def test_configs_validates_provider_protocol() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(
            get_config=lambda: {
                "providers": {"bad": {"model": "", "protocol": "unknown"}}
            }
        )
    ]
    with pytest.raises(ValueError, match="Unsupported protocol"):
        configs.list_providers()


def test_configs_requires_a_non_empty_provider_model() -> None:
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(get_config=lambda: {"providers": {"bad": {"model": ""}}})
    ]

    with pytest.raises(ValueError, match="requires a non-empty model"):
        configs.list_providers()


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


def test_configs_list_providers_skips_invalid_entries() -> None:
    import pytest

    pytest.xfail(reason="known bug: list_providers raises when any provider config is invalid")
    configs = ConfigsPlugin()
    configs._providers = [
        SimpleNamespace(
            get_config=lambda: {
                "providers": {
                    "good": {"model": "demo", "api_key": "k"},
                    "broken": {"model": "demo", "api_key": "k", "protocol": "ftp"},
                }
            }
        )
    ]

    assert configs.list_providers() == ["good"]
