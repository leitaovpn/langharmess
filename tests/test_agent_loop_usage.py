"""Tests for token usage events emitted by the agent loop."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.messages.ai import UsageMetadata

from langharmess_core.agent_loop import PluginAgentLoop, _extract_usage

USAGE: UsageMetadata = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}


class FakeGraph:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def astream(
        self, input_data: Any, config: Any = None, stream_mode: Any = None
    ) -> Any:
        for event in self._events:
            yield event


def test_astream_emits_single_usage_event_after_response() -> None:
    graph = FakeGraph(
        [
            ("messages", (AIMessageChunk(content="hi", id="r1"), "metadata")),
            ("messages", (AIMessageChunk(content="", id="r1", usage_metadata=USAGE), "metadata")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "hi"},
        {"type": "usage", **USAGE},
    ]


def test_astream_accumulates_usage_across_model_runs() -> None:
    run_1: UsageMetadata = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    run_2: UsageMetadata = {"input_tokens": 4, "output_tokens": 1, "total_tokens": 5}
    graph = FakeGraph(
        [
            ("messages", (AIMessageChunk(content="first", id="r1"), "metadata")),
            ("messages", (AIMessageChunk(content="", id="r1", usage_metadata=run_1), "metadata")),
            ("messages", (AIMessageChunk(content="second", id="r2"), "metadata")),
            ("messages", (AIMessageChunk(content="", id="r2", usage_metadata=run_2), "metadata")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "first"},
        {"type": "assistant", "content": "second"},
        {"type": "usage", "input_tokens": 14, "output_tokens": 3, "total_tokens": 17},
    ]


def test_astream_omits_usage_event_when_provider_reports_none() -> None:
    graph = FakeGraph(
        [
            ("messages", (AIMessageChunk(content="hi", id="r1"), "metadata")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "hi"},
    ]


def test_astream_falls_back_to_response_metadata_token_usage() -> None:
    chunk = AIMessageChunk(
        content="",
        id="r1",
        response_metadata={
            "token_usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}
        },
    )
    graph = FakeGraph(
        [
            ("messages", (AIMessageChunk(content="hi", id="r1"), "metadata")),
            ("messages", (chunk, "metadata")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect()) == [
        {"type": "assistant", "content": "hi"},
        {"type": "usage", "input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    ]


def test_usage_chunk_emits_no_assistant_event() -> None:
    # A usage chunk carries content "" with the same message id; the delta
    # must be empty so no assistant event leaks out.
    graph = FakeGraph(
        [
            ("messages", (AIMessageChunk(content="hi", id="r1"), "metadata")),
            ("messages", (AIMessageChunk(content="", id="r1", usage_metadata=USAGE), "metadata")),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    async def collect() -> list[Any]:
        return [chunk async for chunk in loop.astream("hi")]

    assert asyncio.run(collect())[1] == {"type": "usage", **USAGE}


def test_extract_usage_returns_none_without_metadata() -> None:
    assert _extract_usage(SimpleNamespace()) is None


def test_extract_usage_returns_none_for_zero_usage() -> None:
    assert (
        _extract_usage(
            SimpleNamespace(
                usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            )
        )
        is None
    )


def test_extract_usage_reads_usage_metadata() -> None:
    assert _extract_usage(SimpleNamespace(usage_metadata=USAGE)) == USAGE


def test_extract_usage_reads_response_metadata_fallback() -> None:
    message = SimpleNamespace(
        response_metadata={
            "token_usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}
        }
    )
    assert _extract_usage(message) == {
        "input_tokens": 3,
        "output_tokens": 4,
        "total_tokens": 7,
    }
