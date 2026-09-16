"""Regression tests: provider failures must not kill the agent loop component.

A rebind to a broken LLM configuration used to let ``LLMPlugin.get_model()``
raise inside iPOPO's validation callback, which put the loop instance into the
permanent ERRONEOUS state: every later ``/stream`` returned 503
"Agent loop unavailable" until restart.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from langharmess_core.contracts import SPEC_AGENT_DIRECTORY
from langharmess_core.plugin import (
    agent_directory_descriptor,
    agent_loop_template_descriptor,
    agent_plugin_template_descriptor,
    agent_registry_descriptor,
)
from langharmess_core.plugins.loop.agent_loop import PluginAgentLoop
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginRegistry


class StaticModel(BaseChatModel):
    response: str = "ok"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.response))]
        )

    @property
    def _llm_type(self) -> str:
        return "static-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> StaticModel:
        return self


class BrokenLLM:
    def get_model(self) -> Any:
        raise ValueError("Unable to infer model provider for model='broken'")

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": "broken-llm", "version": "1.0.0"}


def test_rebuild_survives_llm_get_model_failure() -> None:
    """A provider exception during graph rebuild clears the graph instead of
    escaping into iPOPO's validation callback."""
    loop = PluginAgentLoop()
    loop._llm_provider = BrokenLLM()

    loop._rebuild()

    assert loop._graph is None


def test_loop_survives_rebind_to_broken_llm_configuration(tmp_path: Any) -> None:
    registry_path = tmp_path / "agents.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "agents": [
                    {
                        "id": "alpha",
                        "name": "Alpha",
                        "description": "first agent",
                        "enabled": True,
                        "created_at": "2026-09-15T00:00:00+00:00",
                        "updated_at": "2026-09-15T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = PluginRegistry(
        [
            agent_plugin_template_descriptor("llm"),
            agent_plugin_template_descriptor("tools"),
            agent_plugin_template_descriptor("name"),
            agent_loop_template_descriptor(),
            agent_registry_descriptor(str(tmp_path)),
            agent_directory_descriptor(),
        ]
    )
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)
        directory = manager.get_service(SPEC_AGENT_DIRECTORY)
        assert directory is not None

        async def scenario() -> tuple[Any, Any, Any]:
            working_model = StaticModel()
            directory.ensure_plugin_instance(
                "alpha", "llm", {"plugin.model.instance": working_model}
            )
            loop_before = directory.get_loop("alpha")
            assert loop_before is not None
            assert loop_before._graph is not None

            # Rebind to a name-only configuration without credentials:
            # get_model() falls back to init_chat_model() and raises.
            directory.ensure_plugin_instance(
                "alpha",
                "llm",
                {"plugin.model.name": "definitely-not-a-provider-xyz"},
            )
            loop_broken = directory.get_loop("alpha")
            return loop_before, loop_broken, working_model

        loop_before, loop_broken, working_model = asyncio.run(scenario())

        # The loop service must survive the broken rebind...
        assert loop_broken is not None
        assert loop_broken._graph is None
        # ...and a later good rebind must restore the graph.
        directory.ensure_plugin_instance(
            "alpha", "llm", {"plugin.model.instance": working_model}
        )
        loop_restored = directory.get_loop("alpha")
        assert loop_restored is not None
        assert loop_restored._graph is not None
    finally:
        manager.stop()
