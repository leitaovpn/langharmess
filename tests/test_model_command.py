"""Interactive model command tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from langharmess_cli.common.interactive import InteractiveCLIRunner
from langharmess_cli.plugins.commands.model import ModelCommandPlugin


def test_model_command_lists_and_switches_providers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin = ModelCommandPlugin()
    command = plugin.get_interactive_commands()[0]
    configs = SimpleNamespace(
        list_providers=lambda: ["alpha", "beta"],
        get_provider=lambda name: {
            "model": "shared-model",
            "protocol": "responses",
            "api_key": f"{name}-key",
            "base_url": f"https://{name}.example/v1/",
        },
    )
    runner = InteractiveCLIRunner(
        base_url="http://api", token="secret", commands=[command], configs=configs
    )
    original_session_id = runner.session_id

    assert runner.onecmd("/model") is False
    assert "alpha, beta" in capsys.readouterr().out
    assert runner.onecmd("/model beta") is False
    assert runner.provider_name == "beta"
    assert runner.model == "shared-model"
    assert runner.model_protocol == "responses"
    assert runner.api_key == "beta-key"
    assert runner.model_base_url == "https://beta.example/v1"
    assert runner.session_id != original_session_id
    assert "beta · shared-model · responses" in runner.renderer.get_status_text()


def test_model_command_reports_unknown_provider(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin = ModelCommandPlugin()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=plugin.get_interactive_commands(),
        configs=SimpleNamespace(
            list_providers=lambda: [], get_provider=lambda name: {}
        ),
    )
    assert runner.onecmd("/model missing") is False
    assert "Unknown provider: missing" in capsys.readouterr().out
    assert plugin.get_commands() == []
    assert plugin.get_plugin_info() == {"name": "model-command", "version": "1.0.0"}


def test_model_command_survives_broken_provider_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from langharmess_config.plugins.configs import ConfigsPlugin

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
    plugin = ModelCommandPlugin()
    runner = InteractiveCLIRunner(
        base_url="http://api",
        token="secret",
        commands=plugin.get_interactive_commands(),
        configs=configs,
    )

    assert runner.onecmd("/model broken") is False
    assert "Error" in capsys.readouterr().out
    assert runner.onecmd("/model") is False
    assert "good" in capsys.readouterr().out
