"""Real Pelix/iPOPO e2e for dynamic plugin discovery and tool exports."""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false

from __future__ import annotations

from pydantic import BaseModel

from langharmess_core.contracts import SPEC_TOOL
from langharmess_core.plugin import tool_export_adapter_template_descriptor
from langharmess_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
from langharmess_plugin.coordinator import RuntimeMutationCoordinator
from langharmess_plugin.discovery import PluginDiscovery
from langharmess_plugin.package import PluginContribution, PluginPackage, ToolExport
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.state_store import InMemoryRuntimeStateStore
from langharmess_scope import ScopeId


class EchoArgs(BaseModel):
    text: str


class EntryPoint:
    def __init__(self, package: PluginPackage, name: str) -> None:
        self.package = package
        self.name = name
        self.value = f"{name}:plugin"

    def load(self):
        return lambda: self.package


def echo_descriptor(name: str, version: str = "1.0.0") -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version=version,
        module="dynamic_plugins.echo",
        factory="dynamic-echo-factory",
        instance=name,
        specification=SPEC_TOOL_EXPORT_TARGET,
        scope="server",
        scope_parent="root",
        enabled=True,
    )


def server_echo_package(version: str = "1.0.0") -> PluginPackage:
    return PluginPackage(
        "example.echo",
        version,
        (
            PluginContribution(
                "echo",
                "server",
                echo_descriptor("server-echo", version=version),
                tool_exports=(ToolExport("server_echo", "Server echo", "echo", EchoArgs),),
            ),
        ),
    )


def agent_echo_package() -> PluginPackage:
    return PluginPackage(
        "example.agent-echo",
        "1.0.0",
        (
            PluginContribution(
                "echo",
                "agent_instance",
                echo_descriptor("agent-echo"),
                tool_exports=(
                    ToolExport(
                        "server_echo",
                        "Agent echo",
                        "echo",
                        EchoArgs,
                        target_scope="agent_instance",
                    ),
                ),
            ),
        ),
    )


def tool_names(manager: PluginManager, scope: str) -> list[str]:
    providers = manager.find_services(
        SPEC_TOOL, manager.scope_filter(ScopeId(scope))
    )
    names: list[str] = []
    for provider in providers:
        names.extend(tool.name for tool in provider.get_tools())
    return names


def make_manager() -> PluginManager:
    manager = PluginManager(
        PluginRegistry(
            [
                PluginDescriptor(
                    name="tools-template",
                    version="1.0.0",
                    module="langharmess_core.plugins.tools.tools",
                    factory="tools-plugin-factory",
                    instance="tools-template",
                    specification=SPEC_TOOL,
                    enabled=False,
                ),
                tool_export_adapter_template_descriptor(),
            ]
        )
    )
    manager.start()
    return manager


def install_templates(manager: PluginManager) -> None:
    for descriptor in manager.registry.list():
        manager.install_plugin(descriptor)
    manager.ensure_scope(ScopeId("agent/a"), name="A", parent_id=ScopeId("agent"))


def make_discovery() -> PluginDiscovery:
    return PluginDiscovery(
        lambda: [
            EntryPoint(server_echo_package(), "echo"),
            EntryPoint(agent_echo_package(), "agent-echo"),
        ]
    )


def test_dynamic_discovery_install_visibility_and_restore() -> None:
    manager = make_manager()
    try:
        install_templates(manager)
        store = InMemoryRuntimeStateStore()
        coordinator = RuntimeMutationCoordinator(manager, store, make_discovery())
        coordinator.rescan()

        coordinator.install("example.echo", "echo")
        coordinator.install(
            "example.agent-echo", "echo", scope_id=ScopeId("agent/a")
        )

        assert "server_echo" in tool_names(manager, "agent")
        assert "server_echo" not in tool_names(manager, "ui")

        agent_properties = manager.service_properties(SPEC_TOOL)
        assert {item.get("plugin.scope_id") for item in agent_properties} == {
            "agent",
            "agent/a",
        }
        ranked = sorted(
            agent_properties,
            key=lambda item: item.get("service.ranking", 0),
            reverse=True,
        )
        assert [item.get("plugin.scope_id") for item in ranked] == [
            "agent/a",
            "agent",
        ]
        tools = []
        for item in ranked:
            provider = manager.find_service(
                SPEC_TOOL,
                f"(plugin.scope_id={item.get('plugin.scope_id')})",
            )
            tools.extend(tool.name for tool in provider.get_tools())
        assert tools.count("server_echo") == 2
    finally:
        manager.stop()

    restored = make_manager()
    try:
        install_templates(restored)
        restarted = RuntimeMutationCoordinator(restored, store, make_discovery())
        restarted.rescan()
        registrations = restarted.restore()
        assert {item.scope_id for item in registrations} == {
            ScopeId("server"),
            ScopeId("agent/a"),
        }
        for scope_id in ("ui", "server", "agent", "agent/a"):
            assert restored.scope_tree.get(ScopeId(scope_id)) is not None
    finally:
        restored.stop()


def test_dynamic_discovery_full_lifecycle() -> None:
    manager = make_manager()
    try:
        install_templates(manager)
        store = InMemoryRuntimeStateStore()
        coordinator = RuntimeMutationCoordinator(manager, store, make_discovery())

        coordinator.rescan()
        assert [item.id for item in coordinator.discovered()] == [
            "example.agent-echo",
            "example.echo",
        ]

        installed = coordinator.install("example.echo", "echo")
        assert installed.descriptor.name == "server-echo"
        assert "server_echo" in tool_names(manager, "agent")

        disabled = coordinator.set_enabled("server-echo", False)
        assert disabled.enabled is False
        assert "server_echo" not in tool_names(manager, "agent")

        enabled = coordinator.set_enabled("server-echo", True)
        assert enabled.enabled is True
        assert "server_echo" in tool_names(manager, "agent")

        coordinator._catalog["example.echo"] = server_echo_package("1.1.0")
        upgraded = coordinator.upgrade("server-echo")
        assert upgraded.package_version == "1.1.0"
        assert upgraded.descriptor.version == "1.1.0"

        coordinator.uninstall("server-echo")
        assert coordinator.registrations() == ()
        assert "server_echo" not in tool_names(manager, "agent")
    finally:
        manager.stop()
