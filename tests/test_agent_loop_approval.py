"""Regression tests for human-approval interrupts in the agent loop.

LangGraph emits interrupt updates as ``{"__interrupt__": (Interrupt(...),)}``
at the top level of the "updates" chunk; older versions nested the same tuple
under the node name.  The loop must forward both shapes as
``approval_required`` events and must never treat the interrupt tuple as a
node-update dict.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from langharness_core.plugins.loop.agent_loop import PluginAgentLoop, _iter_interrupts

APPROVAL_VALUE = {
    "action_requests": [
        {"name": "write_file", "args": {"file_path": "/tmp/x.txt", "text": "hi"}}
    ],
    "review_configs": [],
}


class FakeGraph:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def astream(
        self, input_data: Any, config: Any = None, stream_mode: Any = None
    ) -> Any:
        for event in self._events:
            yield event


def _collect(loop: PluginAgentLoop, **kwargs: Any) -> list[dict[str, Any]]:
    async def scenario() -> list[dict[str, Any]]:
        return [event async for event in loop.astream("go", **kwargs)]

    return asyncio.run(scenario())


def test_astream_forwards_top_level_interrupt_tuple() -> None:
    """The interrupt container is a tuple at the chunk top level; it must be
    forwarded as approval_required instead of being read like a node update."""
    interrupt = SimpleNamespace(value=APPROVAL_VALUE)
    graph = FakeGraph([("updates", {"__interrupt__": (interrupt,)})])
    loop = PluginAgentLoop()
    loop._graph = graph

    events = _collect(loop)

    assert events == [{"type": "approval_required", "request": APPROVAL_VALUE}]


def test_astream_skips_other_non_dict_update_values() -> None:
    """Non-dict values alongside node updates must be skipped, not crashed on."""
    interrupt = SimpleNamespace(value=APPROVAL_VALUE)
    message = AIMessage(content="", tool_calls=[
        {"name": "write_file", "args": {"file_path": "/tmp/x.txt", "text": "hi"}, "id": "c1"}
    ])
    graph = FakeGraph(
        [
            ("updates", {"model": {"messages": [message]}}),
            ("updates", {"__interrupt__": (interrupt,), "model": {"messages": [message]}}),
        ]
    )
    loop = PluginAgentLoop()
    loop._graph = graph

    events = _collect(loop)

    assert events == [
        {"type": "tool_call", "name": "write_file", "tool_call_id": "c1",
         "args": {"file_path": "/tmp/x.txt", "text": "hi"}},
        {"type": "approval_required", "request": APPROVAL_VALUE},
        {"type": "tool_call", "name": "write_file", "tool_call_id": "c1",
         "args": {"file_path": "/tmp/x.txt", "text": "hi"}},
    ]


def test_astream_forwards_interrupt_nested_under_node_name() -> None:
    """Older LangGraph versions nested __interrupt__ under the node name."""
    interrupt = SimpleNamespace(value=APPROVAL_VALUE)
    graph = FakeGraph([("updates", {"tools": {"__interrupt__": (interrupt,)}})])
    loop = PluginAgentLoop()
    loop._graph = graph

    events = _collect(loop)

    assert events == [{"type": "approval_required", "request": APPROVAL_VALUE}]


def test_iter_interrupts_skips_non_dict_containers() -> None:
    assert list(_iter_interrupts(None)) == []
    assert list(_iter_interrupts((1, 2))) == []


class ToolCallModel(BaseChatModel):
    """Always requests the write_file tool."""

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "write_file",
                                "args": {"file_path": "/tmp/x.txt", "text": "hi"},
                                "id": "call-1",
                            }
                        ],
                    )
                )
            ]
        )

    @property
    def _llm_type(self) -> str:
        return "tool-call-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def _approval_loop(executed: list[Any]) -> PluginAgentLoop:
    @tool
    def write_file(file_path: str, text: str) -> str:
        """Write text to a file."""
        executed.append((file_path, text))
        return "written"

    loop = PluginAgentLoop()
    loop._llm_provider = SimpleNamespace(
        get_model=lambda: ToolCallModel(),
        get_plugin_info=lambda: {"name": "fake-llm", "version": "1.0.0"},
    )
    loop._tool_providers = [
        SimpleNamespace(get_tools=lambda: [write_file])
    ]
    loop._middleware_providers = [
        SimpleNamespace(
            get_middlewares=lambda: [
                HumanInTheLoopMiddleware({"write_file": True})
            ]
        )
    ]
    loop._checkpointer_provider = SimpleNamespace(
        get_checkpointer=lambda: InMemorySaver()
    )
    return loop


def test_approval_interrupt_round_trip_with_real_middleware() -> None:
    """End to end: a dangerous tool call interrupts without crashing, and an
    approved decision resumes the graph and executes the tool."""
    executed: list[Any] = []
    loop = _approval_loop(executed)

    async def scenario() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # The graph build needs a running event loop when a checkpointer is
        # configured; the two turns must also share one loop and thread.
        loop._rebuild()
        assert loop._graph is not None
        first = [event async for event in loop.astream("go", thread_id="t1")]
        assert executed == []  # nothing runs before the human approves
        resumed = [
            event
            async for event in loop.astream(
                "",
                thread_id="t1",
                resume={"decisions": [{"type": "approve"}]},
            )
        ]
        return first, resumed

    first, resumed = asyncio.run(scenario())
    approval = [e for e in first if e.get("type") == "approval_required"]
    assert approval, f"expected approval_required in {first}"
    assert approval[0]["request"]["action_requests"][0]["name"] == "write_file"

    outputs = [e for e in resumed if e.get("type") == "tool_output"]
    assert outputs, f"expected tool_output in {resumed}"
    assert outputs[0]["name"] == "write_file"
    assert outputs[0]["output"] == "written"
    assert executed == [("/tmp/x.txt", "hi")]
