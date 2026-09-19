"""Scope tree text rendering tests."""

from typing import Any

from langharness_scope.render import render_scope_tree


def test_render_scope_tree_orders_roots_and_children() -> None:
    scopes: list[dict[str, Any]] = [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "agent", "parent_id": "root", "name": "agent"},
        {"id": "server", "parent_id": "root", "name": "server"},
        {"id": "agent:a", "parent_id": "agent", "name": "A"},
    ]
    assert render_scope_tree(scopes) == (
        "root\n├── agent\n│   └── agent:a\n└── server"
    )


def test_render_scope_tree_handles_empty() -> None:
    assert render_scope_tree([]) == ""


def test_render_scope_tree_sorts_siblings_by_id() -> None:
    scopes: list[dict[str, Any]] = [
        {"id": "root", "parent_id": None, "name": "root"},
        {"id": "z", "parent_id": "root", "name": "z"},
        {"id": "a", "parent_id": "root", "name": "a"},
    ]
    assert render_scope_tree(scopes) == "root\n├── a\n└── z"
