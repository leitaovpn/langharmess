"""ToolExport service wrapping agent registry operations."""

from __future__ import annotations

from typing import Any, Literal

from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel, Field, model_validator

from langharness_core.contracts import AgentRegistryProvider
from langharness_plugin.contracts import ToolExportTarget
from langharness_plugin.package import ToolExport
from langharness_plugin.validation import ContractGuard

AGENT_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
AGENT_ID_HELP = "Agent id matching ^[A-Za-z0-9._-]{1,64}$."


class ListAgentsArgs(BaseModel):
    """Empty schema for the parameterless listing tool."""


class GetAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)


class CreateAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)
    name: str | None = Field(
        default=None, description="Display name; defaults to agent_id."
    )
    description: str | None = Field(
        default=None, description="What this agent is for."
    )


class UpdateAgentArgs(BaseModel):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=AGENT_ID_HELP)
    name: str | None = Field(default=None, description="New display name; omit to keep.")
    description: str | None = Field(default=None, description="New description; omit to keep.")
    enabled: bool | None = Field(default=None, description="Set false to disable; omit to keep.")
    confirm: Literal["DISABLE"] | None = Field(
        default=None,
        description="Required, exactly 'DISABLE', when enabled=false.",
    )

    @model_validator(mode="after")
    def _confirm_required_for_disable(self) -> UpdateAgentArgs:
        if self.enabled is False and self.confirm != "DISABLE":
            raise ValueError("Disabling an agent requires confirm='DISABLE'")
        return self


_LIST_AGENTS_DESCRIPTION = (
    "List every registered agent with its id, name, description, and "
    "enabled state. Use it before get/create/update to learn exact "
    "agent ids. Returns {\"agents\": [...]}, or {\"error\": ...}."
)

_GET_AGENT_DESCRIPTION = (
    "Fetch one agent by id (pattern ^[A-Za-z0-9._-]{1,64}$). Use it to "
    "check an agent's current state before updating it. Returns the "
    "agent dict, or {\"error\": ...}."
)

_CREATE_AGENT_DESCRIPTION = (
    "Create a new agent and bring it online — its plugin set and loop "
    "are materialized automatically. Check list_agents first so the id "
    "does not already exist. name defaults to the id. Returns the "
    "created agent dict, or {\"error\": ...}."
)

_UPDATE_AGENT_DESCRIPTION = (
    "Update an agent's name, description, or enabled state. Only pass "
    "the fields you want to change. Disabling removes the agent's loop "
    "until re-enabled; it is semi-destructive, so enabled=false "
    "requires confirm='DISABLE' exactly. Example: "
    "update_agent(agent_id='billing', description='Handles invoices', "
    "enabled=False, confirm='DISABLE'). Returns the updated agent "
    "dict, or {\"error\": ...}."
)


AGENT_TOOL_EXPORTS: tuple[ToolExport, ...] = (
    ToolExport("list_agents", _LIST_AGENTS_DESCRIPTION, "list_agents", ListAgentsArgs),
    ToolExport("get_agent", _GET_AGENT_DESCRIPTION, "get_agent", GetAgentArgs),
    ToolExport("create_agent", _CREATE_AGENT_DESCRIPTION, "create_agent", CreateAgentArgs),
    ToolExport(
        "update_agent",
        _UPDATE_AGENT_DESCRIPTION,
        "update_agent",
        UpdateAgentArgs,
        destructive=True,
    ),
)


@ComponentFactory("agent-operations-export-factory")
@Provides(ToolExportTarget)
@Property("_plugin_name", "plugin.name", "agent-operations-export")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_registry", AgentRegistryProvider, optional=True, immediate_rebind=True
)
class AgentOperationsExport:
    """Dispatches tool-export operations to the agent registry service."""

    def __init__(self) -> None:
        self._plugin_name = "agent-operations-export"
        self._plugin_version = "1.0.0"
        self._registry: Any = None
        self._guard = ContractGuard(self, "_registry", AgentRegistryProvider)

    @BindField("_registry", if_valid=True)
    def _on_registry_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guard.admit(service):
            return

    @UnbindField("_registry")
    def _on_registry_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guard.release(service)

    def invoke_export(self, operation: str, arguments: dict[str, Any]) -> Any:
        registry = self._registry
        if registry is None:
            return {"error": "Agent registry unavailable"}
        try:
            if operation == "list_agents":
                return {"agents": registry.list_agents()}
            if operation == "get_agent":
                agent = registry.get_agent(str(arguments["agent_id"]))
                if agent is None:
                    return {"error": f"Agent not found: {arguments['agent_id']!r}"}
                return agent
            if operation == "create_agent":
                return registry.create_agent(
                    str(arguments["agent_id"]),
                    str(arguments.get("name") or ""),
                    str(arguments.get("description") or ""),
                )
            if operation == "update_agent":
                fields = {
                    key: arguments[key]
                    for key in ("name", "description", "enabled")
                    if key in arguments and arguments[key] is not None
                }
                return registry.update_agent(str(arguments["agent_id"]), **fields)
            return {"error": f"Unknown operation: {operation}"}
        except ValueError as exc:
            return {"error": str(exc)}

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
