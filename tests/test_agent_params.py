"""Tests for the remaining create_agent parameter plugins."""
# mypy: ignore-errors
# pyright: reportArgumentType=false

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import langharmess_core.agent_loop as agent_loop_module
from langharmess_core.agent_loop import PluginAgentLoop
from langharmess_core.plugins.loop.cache.template_cache import TemplateCachePlugin
from langharmess_core.plugins.loop.checkpointer.sqlite import SQLiteCheckpointerPlugin
from langharmess_core.plugins.loop.checkpointer.template_checkpointer import (
    TemplateCheckpointerPlugin,
)
from langharmess_core.plugins.loop.context_schema.template_context_schema import (
    TemplateContextSchemaPlugin,
)
from langharmess_core.plugins.loop.debug.template_debug import TemplateDebugPlugin
from langharmess_core.plugins.loop.interrupt_after.template_interrupt_after import (
    TemplateInterruptAfterPlugin,
)
from langharmess_core.plugins.loop.interrupt_before.template_interrupt_before import (
    TemplateInterruptBeforePlugin,
)
from langharmess_core.plugins.loop.name.template_name import TemplateAgentNamePlugin
from langharmess_core.plugins.loop.response_format.template_response_format import (
    TemplateResponseFormatPlugin,
)
from langharmess_core.plugins.loop.state_schema.template_state_schema import (
    TemplateStateSchemaPlugin,
)
from langharmess_core.plugins.loop.store.template_store import TemplateStorePlugin
from langharmess_core.plugins.loop.transformers.template_transformers import (
    TemplateTransformersPlugin,
)


def test_agent_parameter_plugins_expose_values() -> None:
    response_format = object()
    state_schema = object()
    context_schema = object()
    checkpointer = object()
    store = object()
    cache = object()

    response = TemplateResponseFormatPlugin()
    response._response_format = response_format
    assert response.get_response_format() is response_format

    state = TemplateStateSchemaPlugin()
    state._state_schema = state_schema
    assert state.get_state_schema() is state_schema

    context = TemplateContextSchemaPlugin()
    context._context_schema = context_schema
    assert context.get_context_schema() is context_schema

    checkpointer_plugin = TemplateCheckpointerPlugin()
    checkpointer_plugin._checkpointer = checkpointer
    assert checkpointer_plugin.get_checkpointer() is checkpointer

    store_plugin = TemplateStorePlugin()
    store_plugin._store = store
    assert store_plugin.get_store() is store

    cache_plugin = TemplateCachePlugin()
    cache_plugin._cache = cache
    assert cache_plugin.get_cache() is cache

    before = TemplateInterruptBeforePlugin()
    before._items = ["a", "b"]
    assert before.get_interrupt_before() == ["a", "b"]

    after = TemplateInterruptAfterPlugin()
    after._items = ["c"]
    assert after.get_interrupt_after() == ["c"]

    debug = TemplateDebugPlugin()
    debug._debug = True
    assert debug.get_debug() is True

    name = TemplateAgentNamePlugin()
    name._agent_name = "my-agent"
    assert name.get_name() == "my-agent"

    transformers = TemplateTransformersPlugin()
    transformers._items = ["t1", "t2"]
    assert transformers.get_transformers() == ["t1", "t2"]


def test_sqlite_checkpointer_is_lazy_and_reused(tmp_path) -> None:
    plugin = SQLiteCheckpointerPlugin()
    plugin._path = str(tmp_path / "nested" / "checkpoints.sqlite3")

    async def exercise() -> None:
        checkpointer = plugin.get_checkpointer()
        assert plugin.get_checkpointer() is checkpointer
        await checkpointer.setup()
        assert plugin.get_plugin_info() == {
            "name": "sqlite-checkpointer",
            "version": "1.0.0",
        }
        plugin._invalidate(object())
        await asyncio.sleep(0)
        plugin._invalidate(object())

    asyncio.run(exercise())
    assert (tmp_path / "nested" / "checkpoints.sqlite3").exists()


def test_agent_loop_collects_list_parameters() -> None:
    loop = PluginAgentLoop()
    loop._interrupt_before_providers = [
        SimpleNamespace(get_interrupt_before=lambda: ["a", "b"]),
        SimpleNamespace(get_interrupt_before=lambda: []),
    ]
    loop._interrupt_after_providers = [
        SimpleNamespace(get_interrupt_after=lambda: ["c"]),
    ]
    loop._transformers_providers = [
        SimpleNamespace(get_transformers=lambda: ["t1"]),
        SimpleNamespace(get_transformers=lambda: ["t2"]),
    ]

    assert loop._collect_interrupt_before() == ["a", "b"]
    assert loop._collect_interrupt_after() == ["c"]
    assert loop._collect_transformers() == ["t1", "t2"]


def test_rebuild_passes_all_parameters_to_create_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_agent(model, tools=None, *, system_prompt=None, **kwargs):
        captured["model"] = model
        captured["tools"] = tools
        captured["system_prompt"] = system_prompt
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_loop_module, "create_agent", fake_create_agent)

    response_format = object()
    state_schema = object()
    context_schema = object()
    checkpointer = object()
    store = object()
    cache = object()

    loop = PluginAgentLoop()
    loop._llm_provider = SimpleNamespace(get_model=lambda: object())
    loop._tool_providers = []
    loop._middleware_providers = []
    loop._system_prompt_providers = []
    loop._response_format_provider = SimpleNamespace(
        get_response_format=lambda: response_format
    )
    loop._state_schema_provider = SimpleNamespace(get_state_schema=lambda: state_schema)
    loop._context_schema_provider = SimpleNamespace(
        get_context_schema=lambda: context_schema
    )
    loop._checkpointer_provider = SimpleNamespace(get_checkpointer=lambda: checkpointer)
    loop._store_provider = SimpleNamespace(get_store=lambda: store)
    loop._interrupt_before_providers = [
        SimpleNamespace(get_interrupt_before=lambda: ["a"]),
    ]
    loop._interrupt_after_providers = [
        SimpleNamespace(get_interrupt_after=lambda: ["b"]),
    ]
    loop._debug_provider = SimpleNamespace(get_debug=lambda: True)
    loop._name_provider = SimpleNamespace(get_name=lambda: "my-agent")
    loop._cache_provider = SimpleNamespace(get_cache=lambda: cache)
    loop._transformers_providers = [
        SimpleNamespace(get_transformers=lambda: ["t1"]),
    ]

    loop._rebuild()

    assert captured["response_format"] is response_format
    assert captured["state_schema"] is state_schema
    assert captured["context_schema"] is context_schema
    assert captured["checkpointer"] is checkpointer
    assert captured["store"] is store
    assert captured["interrupt_before"] == ["a"]
    assert captured["interrupt_after"] == ["b"]
    assert captured["debug"] is True
    assert captured["name"] == "my-agent"
    assert captured["cache"] is cache
    assert captured["transformers"] == ["t1"]
