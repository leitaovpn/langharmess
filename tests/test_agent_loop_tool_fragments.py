"""Regression tests for orphaned tool_use fragments in streamed history."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

from langharness_core.plugins.loop.agent_loop import PluginAgentLoop


class FakeGraph:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def astream(
        self, input_data: Any, config: Any = None, stream_mode: Any = None
    ) -> Any:
        for event in self._events:
            yield event


def _streamed_ai_message() -> AIMessage:
    """One completed tool call plus an orphaned streaming fragment.

    Anthropic-style streaming leaves every partial ``tool_use`` block in
    ``content``; only completed calls are parsed into ``tool_calls``. Replaying
    the orphan makes the API reject the next request with HTTP 400.
    """
    return AIMessage(
        content=[
            {"text": "checking", "type": "text", "index": 0},
            {
                "id": "call_00_done",
                "input": {"dir_path": "."},
                "name": "list_directory",
                "type": "tool_use",
                "index": 1,
                "partial_json": '{"dir_path": "."}',
            },
            {
                "id": "call_01_orphan",
                "input": {},
                "name": "bash",
                "type": "tool_use",
                "index": 2,
                "partial_json": '{"commands": ["ls"]}',
            },
        ],
        tool_calls=[
            {
                "name": "list_directory",
                "args": {"dir_path": "."},
                "id": "call_00_done",
                "type": "tool_call",
            }
        ],
    )


def test_astream_strips_orphaned_tool_use_fragments_from_state() -> None:
    message = _streamed_ai_message()
    graph = FakeGraph([("updates", {"agent": {"messages": [message]}})])
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("go")]

    events = asyncio.run(collect())
    assert events == [
        {"type": "tool_call", "name": "list_directory", "tool_call_id": "call_00_done",
         "args": {"dir_path": "."}},
    ]

    ids = [block.get("id") for block in message.content if isinstance(block, dict)]
    assert "call_01_orphan" not in ids
    assert "call_00_done" in ids


def test_astream_keeps_messages_without_fragments_untouched() -> None:
    message = AIMessage(
        content=[
            {"text": "answer", "type": "text", "index": 0},
            {
                "id": "call_00_done",
                "input": {"dir_path": "."},
                "name": "list_directory",
                "type": "tool_use",
                "index": 1,
                "partial_json": '{"dir_path": "."}',
            },
        ],
        tool_calls=[
            {
                "name": "list_directory",
                "args": {"dir_path": "."},
                "id": "call_00_done",
                "type": "tool_call",
            }
        ],
    )
    graph = FakeGraph([("updates", {"agent": {"messages": [message]}})])
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("go")]

    asyncio.run(collect())
    assert len(message.content) == 2


def test_astream_handles_string_content_and_chunks() -> None:
    chunk = AIMessageChunk(content="plain", id="r1")
    graph = FakeGraph(
        [
            ("messages", (chunk, "metadata")),
            ("updates", {"agent": {"messages": [AIMessage(content="done")]}}),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [{"type": "assistant", "content": "plain"}]
