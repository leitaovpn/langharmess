"""Text rendering for scope trees."""

from __future__ import annotations

from typing import Any


def render_scope_tree(scopes: list[dict[str, Any]]) -> str:
    """Render one indented tree line per scope; children sorted by id."""
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for scope in scopes:
        by_parent.setdefault(scope.get("parent_id"), []).append(scope)
    lines: list[str] = []

    def visit(parent_id: str | None, prefix: str) -> None:
        children = sorted(
            by_parent.get(parent_id) or [], key=lambda item: str(item["id"])
        )
        for index, child in enumerate(children):
            last = index == len(children) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{child['id']}")
            visit(child["id"], prefix + ("    " if last else "│   "))

    for root in sorted(
        by_parent.get(None) or [], key=lambda item: str(item["id"])
    ):
        lines.append(str(root["id"]))
        visit(root["id"], "")
    return "\n".join(lines)
