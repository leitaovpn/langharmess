"""End-to-end tests that start the real Pelix/iPOPO framework."""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from rich.console import Console

from langharmess_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
)
from langharmess_cli.plugins.rich_renderer import RichInteractiveRenderer
from langharmess_core.contracts import (
    SPEC_AGENT_LOOP,
    SPEC_CACHE,
    SPEC_CHECKPOINTER,
    SPEC_CONTEXT_SCHEMA,
    SPEC_DEBUG,
    SPEC_INTERRUPT_AFTER,
    SPEC_INTERRUPT_BEFORE,
    SPEC_NAME,
    SPEC_RESPONSE_FORMAT,
    SPEC_STATE_SCHEMA,
    SPEC_STORE,
    SPEC_SYSTEM_PROMPT,
    SPEC_TRANSFORMERS,
    ToolProvider,
)
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry

CAPTURED_MESSAGES: list[list] = []


class ScriptedToolCallModel(BaseChatModel):
    responses: list[AIMessage]
    i: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        CAPTURED_MESSAGES.append([message for message in messages])
        response = self.responses[self.i]
        self.i = (self.i + 1) % len(self.responses)
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-call-model"

    def bind_tools(self, tools, **kwargs):
        return self


def scripted_tool_call_model() -> ScriptedToolCallModel:
    return ScriptedToolCallModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 2, "b": 3},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The answer is 5."),
        ]
    )


def descriptors(tmp_path: Path) -> PluginRegistry:
    model = scripted_tool_call_model()
    registry = PluginRegistry(
        [
            PluginDescriptor(
                name="llm",
                version="1.0.0",
                module="langharmess_core.plugins.llm.llm",
                factory="llm-plugin-factory",
                instance="llm",
                specification="agent.plugin.llm",
                ranking=100,
                properties={"plugin.model.instance": model},
            ),
            PluginDescriptor(
                name="tools",
                version="1.0.0",
                module="langharmess_core.plugins.tools.tools",
                factory="tools-plugin-factory",
                instance="tools",
                specification="agent.plugin.tools",
            ),
            PluginDescriptor(
                name="middleware",
                version="1.0.0",
                module="langharmess_core.plugins.middleware.template_middleware",
                factory="middleware-plugin-factory",
                instance="middleware",
                specification="agent.plugin.middleware",
            ),
            PluginDescriptor(
                name="system-prompt-a",
                version="1.0.0",
                module="langharmess_core.plugins.system_prompt.template_system_prompt",
                factory="system-prompt-plugin-factory",
                instance="system-prompt-a",
                specification=SPEC_SYSTEM_PROMPT,
                properties={"plugin.system_prompt": "You are A."},
            ),
            PluginDescriptor(
                name="system-prompt-b",
                version="1.0.0",
                module="langharmess_core.plugins.system_prompt.template_system_prompt",
                factory="system-prompt-plugin-factory",
                instance="system-prompt-b",
                specification=SPEC_SYSTEM_PROMPT,
                properties={"plugin.system_prompt": "You are B."},
            ),
            PluginDescriptor(
                name="agent-loop",
                version="1.0.0",
                module="langharmess_core.plugins.loop.agent_loop",
                factory="agent-loop-factory",
                instance="agent-loop",
                specification=SPEC_AGENT_LOOP,
            ),
        ]
    )
    return registry


def test_plugin_lifecycle_and_agent_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = descriptors(tmp_path)
    CAPTURED_MESSAGES.clear()
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)

        loop = manager.get_service(SPEC_AGENT_LOOP)
        assert loop.describe()["tools"] == ["add"]

        result = loop.invoke("What is 2 + 3?")
        assert result["messages"][-1].content == "The answer is 5."
        assert isinstance(CAPTURED_MESSAGES[0][0], SystemMessage)
        assert CAPTURED_MESSAGES[0][0].content == "You are A.\nYou are B."

        llm_props = manager.service_properties("agent.plugin.llm")
        assert llm_props[0]["plugin.version"] == "1.0.0"
        assert manager.get_service("agent.plugin.llm").get_plugin_info()["version"] == "1.0.0"

        manager.unbind_plugin("tools")
        assert loop.describe()["tools"] == []

        manager.bind_plugin("tools")
        assert loop.describe()["tools"] == ["add"]

        manager.uninstall_plugin("middleware")
        assert manager.installed_names() == {
            "llm",
            "tools",
            "agent-loop",
            "system-prompt-a",
            "system-prompt-b",
        }

        workspace_descriptor = PluginDescriptor(
            name="workspace-tools",
            version="1.0.0",
            module="langharmess_core.plugins.tools.workspace",
            factory="workspace-tools-plugin-factory",
            instance="workspace-tools",
            specification="agent.plugin.tools",
            properties={"plugin.tools.root_dir": str(tmp_path)},
        )
        model = manager.get_service("agent.plugin.llm").get_model()
        original_responses = model.responses
        manager.install_plugin(workspace_descriptor)
        try:
            model.responses = [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "tool-proof.txt",
                                "text": "file-tool-ok",
                            },
                            "id": "write-call",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": "tool-proof.txt"},
                            "id": "read-call",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "bash",
                            "args": {"commands": "printf bash-tool-ok"},
                            "id": "bash-call",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="tools completed"),
            ]
            model.i = 0

            tool_result = loop.invoke("Exercise the workspace tools")
            tool_messages = [
                message
                for message in tool_result["messages"]
                if isinstance(message, ToolMessage)
            ]
            assert (tmp_path / "tool-proof.txt").read_text() == "file-tool-ok"
            assert [message.name for message in tool_messages] == [
                "write_file",
                "read_file",
                "bash",
            ]
            assert "file-tool-ok" in str(tool_messages[1].content)
            assert "bash-tool-ok" in str(tool_messages[2].content)
        finally:
            model.responses = original_responses
            model.i = 0
            manager.uninstall_plugin("workspace-tools")

        async def verify_sqlite_memory() -> None:
            sqlite_path = tmp_path / "checkpoints.sqlite3"
            sqlite_descriptor = PluginDescriptor(
                name="sqlite-checkpointer",
                version="1.0.0",
                module="langharmess_core.plugins.checkpointer.sqlite",
                factory="sqlite-checkpointer-plugin-factory",
                instance="sqlite-checkpointer",
                specification=SPEC_CHECKPOINTER,
                properties={"plugin.checkpoint.path": str(sqlite_path)},
            )
            manager.install_plugin(sqlite_descriptor)
            try:
                first_start = len(CAPTURED_MESSAGES)
                _ = [
                    chunk
                    async for chunk in loop.astream(
                        "Remember sqlite-memory", thread_id="memory-thread"
                    )
                ]
                second_start = len(CAPTURED_MESSAGES)
                _ = [
                    chunk
                    async for chunk in loop.astream(
                        "What should you remember?", thread_id="memory-thread"
                    )
                ]

                first_messages = CAPTURED_MESSAGES[first_start]
                second_messages = CAPTURED_MESSAGES[second_start]
                assert len(second_messages) > len(first_messages)
                assert any(
                    getattr(message, "content", "") == "Remember sqlite-memory"
                    for message in second_messages
                )
                assert sqlite_path.exists()
            finally:
                manager.uninstall_plugin("sqlite-checkpointer")
                await asyncio.sleep(0)

        asyncio.run(verify_sqlite_memory())

        captured_kwargs: dict[str, object] = {}

        def fake_create_agent(model, tools=None, *, system_prompt=None, **kwargs):
            captured_kwargs["model"] = model
            captured_kwargs["tools"] = tools
            captured_kwargs["system_prompt"] = system_prompt
            captured_kwargs.update(kwargs)
            return object()

        # Pelix drops a bundle's module from sys.modules on uninstall and
        # re-executes it when another framework installs it again, so patch the
        # module of the class actually in use instead of the imported one.
        monkeypatch.setitem(
            loop._rebuild.__globals__, "create_agent", fake_create_agent
        )

        response_format = object()
        state_schema = object()
        context_schema = object()
        checkpointer = object()
        store = object()
        cache = object()

        parameter_descriptors = [
            PluginDescriptor(
                name="response-format",
                version="1.0.0",
                module="langharmess_core.plugins.response_format.template_response_format",
                factory="response-format-plugin-factory",
                instance="response-format",
                specification=SPEC_RESPONSE_FORMAT,
                properties={"plugin.response_format": response_format},
            ),
            PluginDescriptor(
                name="state-schema",
                version="1.0.0",
                module="langharmess_core.plugins.state_schema.template_state_schema",
                factory="state-schema-plugin-factory",
                instance="state-schema",
                specification=SPEC_STATE_SCHEMA,
                properties={"plugin.state_schema": state_schema},
            ),
            PluginDescriptor(
                name="context-schema",
                version="1.0.0",
                module="langharmess_core.plugins.context_schema.template_context_schema",
                factory="context-schema-plugin-factory",
                instance="context-schema",
                specification=SPEC_CONTEXT_SCHEMA,
                properties={"plugin.context_schema": context_schema},
            ),
            PluginDescriptor(
                name="checkpointer",
                version="1.0.0",
                module="langharmess_core.plugins.checkpointer.template_checkpointer",
                factory="checkpointer-plugin-factory",
                instance="checkpointer",
                specification=SPEC_CHECKPOINTER,
                properties={"plugin.checkpointer": checkpointer},
            ),
            PluginDescriptor(
                name="store",
                version="1.0.0",
                module="langharmess_core.plugins.store.template_store",
                factory="store-plugin-factory",
                instance="store",
                specification=SPEC_STORE,
                properties={"plugin.store": store},
            ),
            PluginDescriptor(
                name="interrupt-before",
                version="1.0.0",
                module="langharmess_core.plugins.interrupt_before.template_interrupt_before",
                factory="interrupt-before-plugin-factory",
                instance="interrupt-before",
                specification=SPEC_INTERRUPT_BEFORE,
                properties={"plugin.interrupt_before": ["before_a", "before_b"]},
            ),
            PluginDescriptor(
                name="interrupt-after",
                version="1.0.0",
                module="langharmess_core.plugins.interrupt_after.template_interrupt_after",
                factory="interrupt-after-plugin-factory",
                instance="interrupt-after",
                specification=SPEC_INTERRUPT_AFTER,
                properties={"plugin.interrupt_after": ["after_a"]},
            ),
            PluginDescriptor(
                name="debug",
                version="1.0.0",
                module="langharmess_core.plugins.debug.template_debug",
                factory="debug-plugin-factory",
                instance="debug",
                specification=SPEC_DEBUG,
                properties={"plugin.debug": True},
            ),
            PluginDescriptor(
                name="agent-name",
                version="1.0.0",
                module="langharmess_core.plugins.name.template_name",
                factory="agent-name-plugin-factory",
                instance="agent-name",
                specification=SPEC_NAME,
                properties={"plugin.agent_name": "my-agent"},
            ),
            PluginDescriptor(
                name="cache",
                version="1.0.0",
                module="langharmess_core.plugins.cache.template_cache",
                factory="cache-plugin-factory",
                instance="cache",
                specification=SPEC_CACHE,
                properties={"plugin.cache": cache},
            ),
            PluginDescriptor(
                name="transformers",
                version="1.0.0",
                module="langharmess_core.plugins.transformers.template_transformers",
                factory="transformers-plugin-factory",
                instance="transformers",
                specification=SPEC_TRANSFORMERS,
                properties={"plugin.transformers": ["transformer_a"]},
            ),
        ]

        for descriptor in parameter_descriptors:
            manager.install_plugin(descriptor)

        # With a checkpointer the graph builds on the API event loop.
        async def rebuild_on_loop() -> None:
            loop._rebuild()

        asyncio.run(rebuild_on_loop())

        assert captured_kwargs["response_format"] is response_format
        assert captured_kwargs["state_schema"] is state_schema
        assert captured_kwargs["context_schema"] is context_schema
        assert captured_kwargs["checkpointer"] is checkpointer
        assert captured_kwargs["store"] is store
        assert captured_kwargs["interrupt_before"] == ["before_a", "before_b"]
        assert captured_kwargs["interrupt_after"] == ["after_a"]
        assert captured_kwargs["debug"] is True
        assert captured_kwargs["name"] == "my-agent"
        assert captured_kwargs["cache"] is cache
        assert captured_kwargs["transformers"] == ["transformer_a"]

        api_descriptors = [
            PluginDescriptor(
                name="api-auth",
                version="1.0.0",
                module="langharmess_api.plugins.auth.auth",
                factory="api-auth-plugin-factory",
                instance="api-auth",
                specification=SPEC_AUTH,
                properties={"plugin.token": "secret"},
            ),
            PluginDescriptor(
                name="api-rate-limit",
                version="1.0.0",
                module="langharmess_api.plugins.rate_limit.rate_limit",
                factory="api-rate-limit-plugin-factory",
                instance="api-rate-limit",
                specification=SPEC_RATE_LIMIT,
                properties={"plugin.limit": 3},
            ),
            PluginDescriptor(
                name="api-db",
                version="1.0.0",
                module="langharmess_api.plugins.db.db",
                factory="api-db-plugin-factory",
                instance="api-db",
                specification=SPEC_DB,
            ),
            PluginDescriptor(
                name="api-health",
                version="1.0.0",
                module="langharmess_api.plugins.routes.health",
                factory="api-health-plugin-factory",
                instance="api-health",
                specification=SPEC_ROUTE,
            ),
            PluginDescriptor(
                name="api-server",
                version="1.0.0",
                module="langharmess_api.plugins.server.app",
                factory="api-server-factory",
                instance="api-server",
                specification=SPEC_API_SERVER,
            ),
        ]

        for descriptor in api_descriptors:
            manager.install_plugin(descriptor)

        api_server = manager.get_service(SPEC_API_SERVER)
        app = api_server.build_app()
        client = TestClient(app)

        assert client.get("/health").status_code == 401
        response = client.get(
            "/health", headers={"Authorization": "Bearer secret"}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "db": True}

        client.get("/health", headers={"Authorization": "Bearer secret"})
        client.get("/health", headers={"Authorization": "Bearer secret"})
        too_many = client.get(
            "/health", headers={"Authorization": "Bearer secret"}
        )
        assert too_many.status_code == 429

        manager.get_service(SPEC_RATE_LIMIT)._hits.clear()

        echo_descriptor = PluginDescriptor(
            name="api-echo",
            version="1.0.0",
            module="langharmess_api.plugins.routes.echo",
            factory="api-echo-plugin-factory",
            instance="api-echo",
            specification=SPEC_ROUTE,
        )
        manager.install_plugin(echo_descriptor)
        app = api_server.build_app()
        dynamic_client = TestClient(app)
        assert dynamic_client.get(
            "/echo", headers={"Authorization": "Bearer secret"}
        ).status_code == 200

        manager.uninstall_plugin("api-echo")
        app = api_server.build_app()
        after_remove_client = TestClient(app)
        assert after_remove_client.get(
            "/echo", headers={"Authorization": "Bearer secret"}
        ).status_code == 404
    finally:
        manager.stop()


def test_real_plugin_agent_stream_renders_response_once(tmp_path: Path) -> None:
    registry = descriptors(tmp_path)
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)

        loop = manager.get_service(SPEC_AGENT_LOOP)

        async def collect():
            return [event async for event in loop.astream("What is 2 + 3?")]

        events = asyncio.run(collect())
        output = StringIO()
        renderer = RichInteractiveRenderer()
        renderer.console = Console(file=output, force_terminal=False, width=100)
        renderer.start_response()
        for event in events:
            renderer.render_event(event)
        renderer.finish_response()

        assert output.getvalue().count("The answer is 5.") == 1
    finally:
        manager.stop()


@pytest.mark.parametrize("protocol", ["chat", "anthropic", "responses"])
def test_agent_loop_invocation_is_unchanged_for_all_protocols(
    tmp_path: Path, protocol: str
) -> None:
    registry = descriptors(tmp_path)
    llm_descriptor = registry.get("llm")
    assert llm_descriptor is not None
    llm_descriptor.properties["plugin.model.protocol"] = protocol
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)

        loop = manager.get_service(SPEC_AGENT_LOOP)
        result = loop.invoke("What is 2 + 3?")

        assert manager.get_service("agent.plugin.llm").get_protocol() == protocol
        assert result["messages"][-1].content == "The answer is 5."
    finally:
        manager.stop()


def test_raw_registered_bad_provider_is_quarantined(tmp_path: Path) -> None:
    registry = descriptors(tmp_path)
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)
        loop = manager.get_service(SPEC_AGENT_LOOP)
        assert loop.describe()["tools"] == ["add"]

        class RawBadToolProvider:
            def get_tools(self, root: str) -> list[Any]:
                return []

            def get_plugin_info(self) -> dict[str, str]:
                return {"name": "raw-bad"}

        manager._context.register_service(ToolProvider, RawBadToolProvider(), {})

        assert manager.get_service("agent.plugin.tools") is not None
        assert loop.describe()["tools"] == ["add"]
        assert len(loop._guards["_tool_providers"].rejected()) == 1
    finally:
        manager.stop()


def test_all_agent_loop_guards_quarantine_raw_bad_services(tmp_path: Path) -> None:
    registry = descriptors(tmp_path)
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)
        loop = manager.get_service(SPEC_AGENT_LOOP)

        fields = [field for field in loop._guards if field != "_llm_provider"]
        fields.append("_llm_provider")  # A rejected required LLM invalidates the loop; run last.
        for index, field in enumerate(fields):
            guard = loop._guards[field]
            bad_service = object()
            manager._context.register_service(
                guard.protocol,
                bad_service,
                {"service.ranking": 10_000 + index},
            )
            assert id(bad_service) in guard.rejected(), field
    finally:
        manager.stop()


def test_all_api_and_config_guards_quarantine_raw_bad_services(tmp_path: Path) -> None:
    registry = descriptors(tmp_path)
    manager = PluginManager(registry)
    manager.start()
    try:
        for item in registry.list():
            manager.install_plugin(item)

        extra_descriptors = [
            PluginDescriptor(
                name="configs",
                version="1.0.0",
                module="langharmess_config.plugins.configs",
                factory="configs-plugin-factory",
                instance="configs",
                specification="configs",
            ),
            PluginDescriptor(
                name="api-stream",
                version="1.0.0",
                module="langharmess_api.plugins.routes.stream",
                factory="api-stream-route-factory",
                instance="api-stream",
                specification=SPEC_ROUTE,
            ),
            PluginDescriptor(
                name="api-server",
                version="1.0.0",
                module="langharmess_api.plugins.server.app",
                factory="api-server-factory",
                instance="api-server",
                specification=SPEC_API_SERVER,
            ),
        ]
        for item in extra_descriptors:
            manager.install_plugin(item)

        api_server = manager.get_service(SPEC_API_SERVER)
        stream_route = next(
            provider
            for provider in manager.get_services(SPEC_ROUTE)
            if hasattr(provider, "get_plugin_info")
            and provider.get_plugin_info()["name"] == "stream"
        )
        configs = manager.get_service("configs")

        for field, guard in api_server._guards.items():
            bad_service = object()
            registration = manager._context.register_service(
                guard.protocol,
                bad_service,
                {"service.ranking": 10_000},
            )
            assert id(bad_service) in guard.rejected(), field
            value = getattr(api_server, field)
            assert bad_service is not value
            assert not isinstance(value, list) or all(
                item is not bad_service for item in value
            )
            registration.unregister()

        for field, guard in stream_route._guards.items():
            bad_service = object()
            registration = manager._context.register_service(
                guard.protocol,
                bad_service,
                {"service.ranking": 10_000},
            )
            assert id(bad_service) in guard.rejected(), field
            assert getattr(stream_route, field) is not bad_service
            registration.unregister()

        bad_config_provider = object()
        registration = manager._context.register_service(
            configs._guard.protocol,
            bad_config_provider,
            {},
        )
        assert id(bad_config_provider) in configs._guard.rejected()
        assert all(item is not bad_config_provider for item in configs._providers)
        registration.unregister()
    finally:
        manager.stop()
