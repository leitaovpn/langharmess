"""Scope visibility and resolution rules for scoped plugins."""

from __future__ import annotations

from langharmess_plugin.scope_policy import (
    PluginCandidate,
    PluginScopePolicy,
    resolve_scoped_aggregate,
)
from langharmess_scope import ScopeId, ScopeTree


def hierarchy() -> tuple[ScopeTree, ScopeId, ScopeId, ScopeId]:
    tree = ScopeTree()
    root = ScopeId("root")
    agent = ScopeId("agent")
    session = ScopeId("session")
    tree.create(agent, "Agent", root)
    tree.create(session, "Session", agent)
    return tree, root, agent, session


def candidate(scope: ScopeId, key: str, ranking: int, service: str) -> PluginCandidate:
    return PluginCandidate(scope, key, ranking, service)


def test_visible_scopes_are_self_then_ancestors() -> None:
    tree, root, agent, session = hierarchy()
    policy = PluginScopePolicy(tree)

    assert policy.visible_scopes(session) == (session, agent, root)
    assert policy.visible_scopes(root) == (root,)


def test_requires_best_prefers_nearest_scope_then_descriptor_ranking() -> None:
    tree, root, agent, session = hierarchy()
    policy = PluginScopePolicy(tree)
    candidates = [
        candidate(root, "root-high", 1000, "root"),
        candidate(agent, "low", 1, "agent-low"),
        candidate(agent, "high", 2, "agent-high"),
        candidate(ScopeId("sibling"), "hidden", 9999, "hidden"),
    ]

    selected = policy.resolve_best(session, candidates)
    assert selected is not None
    assert selected.service == "agent-high"


def test_requires_aggregates_visible_plugins_with_nearest_key_override() -> None:
    tree, root, agent, session = hierarchy()
    policy = PluginScopePolicy(tree)
    candidates = [
        candidate(root, "filesystem", 5, "root-files"),
        candidate(root, "clock", 0, "root-clock"),
        candidate(agent, "filesystem", 1, "agent-files"),
        candidate(session, "temporary", 0, "session-temp"),
        candidate(ScopeId("sibling"), "hidden", 0, "hidden"),
    ]

    resolved = policy.resolve_aggregate(session, candidates)

    assert [item.service for item in resolved] == [
        "session-temp",
        "agent-files",
        "root-clock",
    ]


def test_visibility_filter_escapes_scope_ids() -> None:
    tree = ScopeTree()
    child = ScopeId("agent*(one)")
    tree.create(child, "Agent")

    assert PluginScopePolicy(tree).visibility_filter(child) == (
        "(|(plugin.scope_id=agent\\2a\\28one\\29)(plugin.scope_id=root))"
    )


def test_injected_aggregate_keeps_nearest_provider_for_each_key() -> None:
    root_files = object()
    root_clock = object()
    agent_files = object()
    legacy = object()
    providers = [root_files, root_clock, agent_files, legacy]
    metadata = {
        id(root_files): ("root", "filesystem", 100),
        id(root_clock): ("root", "clock", 0),
        id(agent_files): ("agent", "filesystem", 1),
    }

    assert resolve_scoped_aggregate(
        ["agent", "root"], providers, metadata
    ) == [agent_files, root_clock, legacy]
