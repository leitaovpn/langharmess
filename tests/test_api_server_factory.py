"""Tests for the standalone API server factory."""
# mypy: ignore-errors

from __future__ import annotations

from types import SimpleNamespace

import pytest

import langharmess_api.server as server_module


def test_create_app_uses_plugin_manager_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_module, "_MANAGER", None)

    manager = SimpleNamespace(
        get_service=lambda spec: SimpleNamespace(
            build_app=lambda: SimpleNamespace(title="ok")
        )
    )

    def fake_manager(registry):
        manager.start = lambda: None
        manager.install_plugin = lambda descriptor: None
        return manager

    monkeypatch.setattr(server_module, "PluginManager", fake_manager)
    monkeypatch.setattr(
        server_module,
        "PluginRegistry",
        lambda descriptors: SimpleNamespace(list=lambda: descriptors),
    )

    app = server_module.create_app()
    assert app.title == "ok"
    assert server_module._MANAGER is manager

    second_app = server_module.create_app()
    assert second_app.title == "ok"
