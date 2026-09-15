"""Real Pelix/iPOPO lifecycle coverage for hierarchical plugin scopes."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from langharmess_core.contracts import SPEC_AGENT_LOOP, SPEC_LLM, SPEC_TOOL
from langharmess_core.plugin import agent_loop_descriptor
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_scope import InMemoryScopeStore, ScopeId, ScopeTree


class ScopeModel(BaseChatModel):
    label: str

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.label))]
        )

    @property
    def _llm_type(self) -> str:
        return "scope-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScopeModel:
        return self


def root_shared() -> str:
    """Return the root implementation."""
    return "root"


def agent_shared() -> str:
    """Return the nearer agent implementation."""
    return "agent"


def root_other() -> str:
    """Return a non-shadowed root implementation."""
    return "other"


def template(
    name: str, module: str, factory: str, specification: str
) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module=module,
        factory=factory,
        instance=name,
        specification=specification,
        enabled=False,
    )


def instance(
    name: str,
    module: str,
    factory: str,
    specification: str,
    *,
    ranking: int = 0,
    properties: dict[str, Any] | None = None,
) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version="1.0.0",
        module=module,
        factory=factory,
        instance=name,
        specification=specification,
        ranking=ranking,
        properties=properties or {},
    )


def test_scope_and_plugin_full_lifecycle_with_best_and_aggregate_shadowing() -> None:
    registry = PluginRegistry(
        [
            template(
                "llm-template",
                "langharmess_core.plugins.llm.llm",
                "llm-plugin-factory",
                SPEC_LLM,
            ),
            template(
                "tools-template",
                "langharmess_core.plugins.tools.tools",
                "tools-plugin-factory",
                SPEC_TOOL,
            ),
            template(
                "loop-template",
                "langharmess_core.plugins.loop.agent_loop",
                "agent-loop-factory",
                SPEC_AGENT_LOOP,
            ),
        ]
    )
    scope_store = InMemoryScopeStore()
    manager = PluginManager(registry, scope_tree=ScopeTree(scope_store))
    manager.start()
    try:
        for descriptor in registry.list():
            manager.install_plugin(descriptor)
        manager.ensure_scope(ScopeId("agent"), name="Agent")
        manager.ensure_scope(
            ScopeId("session"), name="Session", parent_id=ScopeId("agent")
        )
        restored = ScopeTree(scope_store)
        assert [scope.id for scope in restored.ancestors(ScopeId("session"))] == [
            ScopeId("agent"),
            ScopeId("root"),
        ]

        manager.instantiate_instance(
            instance(
                "llm@root",
                "langharmess_core.plugins.llm.llm",
                "llm-plugin-factory",
                SPEC_LLM,
                ranking=999,
                properties={"plugin.model.instance": ScopeModel(label="root")},
            ),
            scope_id=ScopeId("root"),
            plugin_key="llm",
        )
        agent_model = ScopeModel(label="agent")
        manager.instantiate_instance(
            instance(
                "llm@agent",
                "langharmess_core.plugins.llm.llm",
                "llm-plugin-factory",
                SPEC_LLM,
                ranking=1,
                properties={"plugin.model.instance": agent_model},
            ),
            scope_id=ScopeId("agent"),
            plugin_key="llm",
        )
        for name, scope, key, function in [
            ("shared@root", "root", "shared", root_shared),
            ("other@root", "root", "other", root_other),
            ("shared@agent", "agent", "shared", agent_shared),
        ]:
            manager.instantiate_instance(
                instance(
                    name,
                    "langharmess_core.plugins.tools.tools",
                    "tools-plugin-factory",
                    SPEC_TOOL,
                    properties={"plugin.tools.functions": [function]},
                ),
                scope_id=ScopeId(scope),
                plugin_key=key,
            )

        visible = manager.scope_filter(ScopeId("session"))
        loop_descriptor = agent_loop_descriptor(
            "session", [SPEC_LLM, SPEC_TOOL], visibility_filter=visible
        )
        manager.instantiate_instance(
            loop_descriptor,
            scope_id=ScopeId("session"),
            plugin_key="agent-loop",
        )
        loop = manager.find_service(
            SPEC_AGENT_LOOP, "(plugin.scope_id=session)"
        )

        llm_properties = manager.service_properties(SPEC_LLM)
        assert [
            (item.get("plugin.scope_id"), item.get("service.ranking"))
            for item in llm_properties
        ] == [("agent", 1_000_001), ("root", 999)]
        assert manager.find_service(SPEC_LLM, visible).get_model() is agent_model
        assert loop._llm_provider.get_model() is agent_model, llm_properties
        assert [tool.name for tool in loop._collect_tools()] == [
            "agent_shared",
            "root_other",
        ], (loop._scope_chain, loop._service_metadata)

        manager.kill_instance("shared@agent")
        assert [tool.name for tool in loop._collect_tools()] == [
            "root_other",
            "root_shared",
        ]

        manager.remove_scope(ScopeId("agent"), recursive=True)
        assert manager.scope_tree.get(ScopeId("agent")) is None
        assert ScopeTree(scope_store).get(ScopeId("agent")) is None
        assert manager.find_service(
            SPEC_AGENT_LOOP, "(plugin.scope_id=session)"
        ) is None
        assert set(manager.scoped_instances()) == {
            "llm@root",
            "shared@root",
            "other@root",
        }

        for name in tuple(manager.scoped_instances()):
            manager.kill_instance(name)
        for name in tuple(manager.installed_names()):
            manager.uninstall_plugin(name)
        assert manager.installed_names() == set()
        assert manager.installed_modules() == set()
    finally:
        manager.stop()
