"""Plugin-specific visibility and shadowing rules over a generic scope tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langharmess_plugin.scope_const import PLUGIN_KEY, PLUGIN_SCOPE_ID
from langharmess_scope import ScopeId, ScopeTreeProvider


@dataclass(frozen=True, slots=True)
class PluginCandidate:
    scope_id: ScopeId
    plugin_key: str
    ranking: int
    service: Any


def _escape_ldap(value: str) -> str:
    replacements = {"\\": "\\5c", "*": "\\2a", "(": "\\28", ")": "\\29", "\0": "\\00"}
    return "".join(replacements.get(character, character) for character in value)


class PluginScopePolicy:
    """Applies ancestor visibility to best and aggregate plugin requirements."""

    def __init__(self, tree: ScopeTreeProvider) -> None:
        self._tree = tree

    def visible_scopes(self, consumer_scope: ScopeId) -> tuple[ScopeId, ...]:
        return tuple(
            scope.id
            for scope in self._tree.ancestors(consumer_scope, include_self=True)
        )

    def visibility_filter(self, consumer_scope: ScopeId) -> str:
        clauses = "".join(
            f"({PLUGIN_SCOPE_ID}={_escape_ldap(str(scope_id))})"
            for scope_id in self.visible_scopes(consumer_scope)
        )
        return f"(|{clauses})"

    def resolve_best(
        self,
        consumer_scope: ScopeId,
        candidates: list[PluginCandidate],
    ) -> PluginCandidate | None:
        distance = {
            scope_id: index
            for index, scope_id in enumerate(self.visible_scopes(consumer_scope))
        }
        visible = [item for item in candidates if item.scope_id in distance]
        if not visible:
            return None
        return min(
            visible,
            key=lambda item: (
                distance[item.scope_id],
                -item.ranking,
                item.plugin_key,
            ),
        )

    def resolve_aggregate(
        self,
        consumer_scope: ScopeId,
        candidates: list[PluginCandidate],
    ) -> tuple[PluginCandidate, ...]:
        resolved: list[PluginCandidate] = []
        seen: set[str] = set()
        for scope_id in self.visible_scopes(consumer_scope):
            local = sorted(
                (item for item in candidates if item.scope_id == scope_id),
                key=lambda item: (-item.ranking, item.plugin_key),
            )
            for item in local:
                if item.plugin_key not in seen:
                    seen.add(item.plugin_key)
                    resolved.append(item)
        return tuple(resolved)


def resolve_scoped_aggregate(
    visible_scopes: list[str],
    providers: list[Any],
    metadata: dict[int, tuple[str, str, int]],
) -> list[Any]:
    """Apply nearest-scope key shadowing to an injected aggregate."""
    if not visible_scopes:
        return list(providers)
    distance = {scope_id: index for index, scope_id in enumerate(visible_scopes)}
    complete = dict(metadata)
    for provider in providers:
        scope_id = getattr(provider, "_plugin_scope_id", None)
        plugin_key = getattr(provider, "_plugin_key", None)
        if id(provider) not in complete and scope_id is not None and plugin_key is not None:
            complete[id(provider)] = (
                str(scope_id),
                str(plugin_key),
                int(getattr(provider, "_plugin_ranking", 0)),
            )
    legacy = [provider for provider in providers if id(provider) not in complete]
    scoped = [
        (provider, complete[id(provider)])
        for provider in providers
        if id(provider) in complete and complete[id(provider)][0] in distance
    ]
    scoped.sort(
        key=lambda item: (distance[item[1][0]], -item[1][2], item[1][1])
    )
    selected: list[Any] = []
    seen: set[str] = set()
    for provider, (_, plugin_key, _) in scoped:
        if plugin_key not in seen:
            seen.add(plugin_key)
            selected.append(provider)
    return selected + legacy


def resolve_scoped_best(
    visible_scopes: list[str],
    providers: list[Any],
    metadata: dict[int, tuple[str, str, int]],
) -> Any | None:
    """Choose the nearest visible provider, then the highest local ranking."""
    distance = {scope_id: index for index, scope_id in enumerate(visible_scopes)}
    complete = dict(metadata)
    for provider in providers:
        scope_id = getattr(provider, "_plugin_scope_id", None)
        plugin_key = getattr(provider, "_plugin_key", None)
        if id(provider) not in complete and scope_id is not None and plugin_key is not None:
            complete[id(provider)] = (
                str(scope_id),
                str(plugin_key),
                int(getattr(provider, "_plugin_ranking", 0)),
            )
    scoped = [
        provider
        for provider in providers
        if id(provider) in complete and complete[id(provider)][0] in distance
    ]
    if not scoped:
        return None
    return min(
        scoped,
        key=lambda provider: (
            distance[complete[id(provider)][0]],
            -complete[id(provider)][2],
            complete[id(provider)][1],
        ),
    )
