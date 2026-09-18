"""LangChain tools wrapping the runtime plugin-management coordinator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Property,
    Provides,
    RequiresBest,
    UnbindField,
)
from pydantic import BaseModel, Field, field_validator

from langharmess_core.contracts import ToolProvider
from langharmess_plugin.contracts import DynamicPluginManager
from langharmess_plugin.validation import ContractGuard, is_runtime_scope
from langharmess_scope.render import render_scope_tree

SCOPE_HELP = (
    "Explicit runtime scope: root, server, ui, agent, or agent:<id>. "
    "The bare prefix 'agent:' is rejected."
)


class NoArgs(BaseModel):
    """Empty schema for parameterless tools."""


class RuntimeScopeArgs(BaseModel):
    """Base schema requiring an explicit, valid runtime scope."""

    scope: str = Field(description=SCOPE_HELP)

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str) -> str:
        if not is_runtime_scope(value):
            raise ValueError(f"Unknown runtime scope: {value!r}")
        return value


class ListRuntimePluginsArgs(BaseModel):
    """Optional scope filter; omit to aggregate every runtime scope."""

    scope: str | None = Field(
        default=None, description=f"Optional filter. {SCOPE_HELP}"
    )

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str | None) -> str | None:
        if value is not None and not is_runtime_scope(value):
            raise ValueError(f"Unknown runtime scope: {value!r}")
        return value


def _registration_summary(registration: Any) -> dict[str, Any]:
    """Safe registration view; never serializes embedded service objects."""
    return {
        "name": registration.descriptor.name,
        "package_id": registration.package_id,
        "contribution_id": registration.contribution_id,
        "version": registration.package_version,
        "scope_id": str(registration.scope_id),
        "enabled": registration.enabled,
        "status": registration.status,
        "specification": registration.descriptor.specification,
    }


def _discovered_summary(package: Any) -> dict[str, Any]:
    return {
        "package_id": package.id,
        "version": package.version,
        "contributions": [
            {
                "id": item.id,
                "name": item.descriptor.name,
                "target": item.target,
                "module": item.descriptor.module,
                "specification": item.descriptor.specification,
            }
            for item in package.contributions
        ],
    }


def _guard(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run a mutation and map coordinator errors to a readable dict."""
    try:
        return action()
    except (KeyError, ValueError, RuntimeError) as exc:
        return {"error": str(exc)}


@ComponentFactory("management-tools-plugin-factory")
@Provides(ToolProvider)
@Property("_plugin_name", "plugin.name", "management-tools-plugin")
@Property("_plugin_version", "plugin.version", "1.0.0")
@RequiresBest(
    "_dynamic_manager", DynamicPluginManager, optional=True, immediate_rebind=True
)
class ManagementToolsPlugin:
    """Exposes runtime plugin-management operations as LangChain tools."""

    def __init__(self) -> None:
        self._plugin_name = "management-tools-plugin"
        self._plugin_version = "1.0.0"
        self._dynamic_manager: Any = None
        self._guard = ContractGuard(self, "_dynamic_manager", DynamicPluginManager)

    @BindField("_dynamic_manager", if_valid=True)
    def _on_manager_bind(self, field: str, service: Any, reference: Any) -> None:
        if not self._guard.admit(service):
            return

    @UnbindField("_dynamic_manager")
    def _on_manager_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._guard.release(service)

    def get_tools(self) -> list[Any]:
        manager = self._dynamic_manager
        if manager is None:
            return []
        return [
            self._scope_tree_tool(manager),
            self._list_tool(manager),
            self._discover_tool(manager),
        ]

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}

    @staticmethod
    def _scope_tree_tool(manager: Any) -> StructuredTool:
        def list_scope_tree() -> dict[str, Any]:
            scopes = [
                {
                    "id": str(scope.id),
                    "parent_id": (
                        str(scope.parent_id)
                        if scope.parent_id is not None
                        else None
                    ),
                    "name": scope.name,
                }
                for scope in manager.scopes()
            ]
            return {"scope_tree": render_scope_tree(scopes)}

        return StructuredTool.from_function(
            func=list_scope_tree,
            name="list_scope_tree",
            description=(
                "Show the runtime scope tree (root/server/ui/agent/"
                "agent:<id>) with parent-child structure. Use it to "
                "understand scope topology before targeting plugin "
                "operations, because every plugin mutation requires an "
                "explicit scope. Returns {\"scope_tree\": <text tree>}, "
                "or {\"error\": ...}."
            ),
            args_schema=NoArgs,
        )

    @staticmethod
    def _list_tool(manager: Any) -> StructuredTool:
        def list_runtime_plugins(scope: str | None = None) -> dict[str, Any]:
            registrations = manager.registrations()
            if scope is not None:
                registrations = [
                    item for item in registrations if str(item.scope_id) == scope
                ]
            return {
                "plugins": [_registration_summary(item) for item in registrations]
            }

        return StructuredTool.from_function(
            func=list_runtime_plugins,
            name="list_runtime_plugins",
            description=(
                "List installed runtime plugins, optionally filtered by "
                "scope (omit to aggregate every runtime scope). Use it "
                "before enable/disable/upgrade/uninstall to learn the exact "
                "registered plugin names and scopes, because mutations "
                "match by (name, scope). Returns {\"plugins\": [{name, "
                "scope_id, enabled, status, package_id, contribution_id, "
                "specification}]}, or {\"error\": ...}."
            ),
            args_schema=ListRuntimePluginsArgs,
        )

    @staticmethod
    def _discover_tool(manager: Any) -> StructuredTool:
        def discover_plugins() -> dict[str, Any]:
            manager.rescan()
            return {
                "packages": [
                    _discovered_summary(item) for item in manager.discovered()
                ]
            }

        return StructuredTool.from_function(
            func=discover_plugins,
            name="discover_plugins",
            description=(
                "Rescan the plugin catalog and list discoverable packages "
                "with their contributions. Always run this before "
                "install_plugin to obtain valid package_id/contribution_id "
                "pairs. Returns {\"packages\": [{package_id, version, "
                "contributions: [{id, name, target, module, "
                "specification}]}]}, or {\"error\": ...}."
            ),
            args_schema=NoArgs,
        )
