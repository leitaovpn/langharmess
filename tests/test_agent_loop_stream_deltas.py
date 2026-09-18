"""Regression tests for streamed assistant delta forwarding."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessageChunk

from langharness_core.plugins.loop.agent_loop import PluginAgentLoop


class FakeGraph:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def astream(
        self, input_data: Any, config: Any = None, stream_mode: Any = None
    ) -> Any:
        for event in self._events:
            yield event


def _chunk(content: str, message_id: str = "m1") -> tuple[AIMessageChunk, str]:
    return AIMessageChunk(content=content, id=message_id), "metadata"


def _assistant_deltas(loop: PluginAgentLoop) -> list[str]:
    async def collect() -> list[str]:
        events = [event async for event in loop.astream("go")]
        return [
            str(event["content"])
            for event in events
            if event.get("type") == "assistant"
        ]

    return asyncio.run(collect())


def test_astream_forwards_consecutive_identical_deltas() -> None:
    """Chat-protocol providers stream per-token deltas; two identical deltas in
    a row (e.g. the two '7' tokens of '77') must both be forwarded."""
    graph = FakeGraph(
        [
            ("messages", _chunk("scope")),
            ("messages", _chunk("-marker")),
            ("messages", _chunk("-")),
            ("messages", _chunk("7")),
            ("messages", _chunk("7")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    deltas = _assistant_deltas(loop)

    assert deltas == ["scope", "-marker", "-", "7", "7"]
    assert "".join(deltas) == "scope-marker-77"


def test_astream_forwards_cumulative_content_as_deltas() -> None:
    """Anthropic-style cumulative chunks still yield only the new suffix."""
    graph = FakeGraph(
        [
            ("messages", _chunk("scope")),
            ("messages", _chunk("scope-marker")),
            ("messages", _chunk("scope-marker-77")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    deltas = _assistant_deltas(loop)

    assert deltas == ["scope", "-marker", "-77"]
    assert "".join(deltas) == "scope-marker-77"
