"""Module boundary exposed by the agent subsystem."""

from __future__ import annotations

from typing import Any, cast

from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Provides,
    RequiresBest,
    UnbindField,
)

from langharness_core.contracts import AgentDirectoryProvider, AgentServerProvider
from langharness_plugin.contracts import DynamicPluginManager
from langharness_plugin.validation import ContractGuard


@ComponentFactory("agent-server-factory")
@Provides(AgentServerProvider)
@RequiresBest("_directory", AgentDirectoryProvider, optional=True, immediate_rebind=True)
@RequiresBest("_plugins", DynamicPluginManager, optional=True, immediate_rebind=True)
class AgentServerService:
    def __init__(self) -> None:
        self._directory: Any = None
        self._plugins: Any = None
        self._guards = {
            "_directory": ContractGuard(self, "_directory", AgentDirectoryProvider),
            "_plugins": ContractGuard(self, "_plugins", DynamicPluginManager),
        }

    @BindField("_directory", if_valid=True)
    @BindField("_plugins", if_valid=True)
    def _on_bind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].admit(service)

    @UnbindField("_directory")
    @UnbindField("_plugins")
    def _on_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guards[field].release(service)

    def _require_directory(self) -> AgentDirectoryProvider:
        if self._directory is None:
            raise RuntimeError("Agent directory is unavailable")
        return cast_agent_directory(self._directory)

    def list_agents(self) -> list[dict[str, Any]]:
        return self._require_directory().list_agents()

    def get_loop(self, agent_id: str) -> Any | None:
        return self._require_directory().get_loop(agent_id)

    def reload(self, agent_id: str | None = None) -> None:
        self._require_directory().reload(agent_id)

    def replace_loop_package(self, package_id: str, contribution_id: str) -> None:
        if self._plugins is None:
            raise RuntimeError("Dynamic plugin manager is unavailable")
        self._plugins.install(package_id, contribution_id)
        self.reload()


def cast_agent_directory(value: Any) -> AgentDirectoryProvider:
    return cast(AgentDirectoryProvider, value)
