"""Tests for the scope tree route."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from langharness_api.plugins.routes.scopes import ScopesRoutePlugin
from langharness_scope import Scope, ScopeId


class FakeDynamic:
    def rescan(self) -> Any:
        return None

    def discovered(self) -> tuple[Any, ...]:
        return ()

    def registrations(self) -> tuple[Any, ...]:
        return ()

    def install(self, package_id, contribution_id, *, scope_id=None):
        raise NotImplementedError

    def set_enabled(self, name, enabled):
        raise NotImplementedError

    def uninstall(self, name):
        raise NotImplementedError

    def upgrade(self, name):
        raise NotImplementedError

    def scopes(self) -> tuple[Scope, ...]:
        return (
            Scope(ScopeId("root"), None, "root"),
            Scope(ScopeId("ui"), ScopeId("root"), "UI"),
            Scope(ScopeId("agent"), ScopeId("root"), "Agent"),
            Scope(ScopeId("agent:a"), ScopeId("agent"), "A"),
        )


def make_plugin() -> ScopesRoutePlugin:
    plugin = ScopesRoutePlugin()
    plugin._dynamic = FakeDynamic()
    return plugin


def make_client(plugin: ScopesRoutePlugin) -> TestClient:
    app = FastAPI()
    app.include_router(plugin.get_router())
    return TestClient(app)


def test_get_scope_returns_the_tree() -> None:
    response = make_client(make_plugin()).get("/scope")
    assert response.status_code == 200
    assert response.json() == {
        "scopes": [
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "ui", "parent_id": "root", "name": "UI"},
            {"id": "agent", "parent_id": "root", "name": "Agent"},
            {"id": "agent:a", "parent_id": "agent", "name": "A"},
        ]
    }


def test_get_scope_returns_503_without_dynamic_manager() -> None:
    plugin = ScopesRoutePlugin()
    response = make_client(plugin).get("/scope")
    assert response.status_code == 503


def test_plugin_info_is_exposed() -> None:
    assert make_plugin().get_plugin_info() == {"name": "scopes", "version": "1.0.0"}
