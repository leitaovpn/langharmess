"""Transactional dynamic plugin mutation behavior."""
# mypy: ignore-errors

from __future__ import annotations

from unittest.mock import Mock

import pytest

from langharness_plugin.contracts import SPEC_TOOL_EXPORT_TARGET
from langharness_plugin.coordinator import (
    RuntimeMutationCoordinator,
    RuntimeMutationError,
)
from langharness_plugin.discovery import PluginDiscovery
from langharness_plugin.package import PluginContribution, PluginPackage, ToolExport
from langharness_plugin.registry import PluginDescriptor, PluginRegistry
from langharness_plugin.state_store import (
    InMemoryRuntimeStateStore,
    PersistedPluginRegistration,
    RuntimeStateSnapshot,
)
from langharness_scope import ROOT_SCOPE_ID, ScopeId, ScopeTree


class EntryPoint:
    def __init__(self, package: PluginPackage, name: str = "dynamic") -> None:
        self.package = package
        self.name = name
        self.value = f"{name}:package"

    def load(self):
        return lambda: self.package


class FakeTarget:
    def invoke_export(self, operation, arguments):
        return {"operation": operation, "arguments": arguments}


def descriptor(
    name: str,
    *,
    version: str = "1",
    specification: str = "dynamic.service",
    scope: str = "server",
    scope_parent: str = "root",
    enabled: bool = True,
) -> PluginDescriptor:
    return PluginDescriptor(
        name=name,
        version=version,
        module="dynamic.module",
        factory="dynamic-factory",
        instance=name,
        specification=specification,
        scope=scope,
        scope_parent=scope_parent,
        swap_policy="hot",
        enabled=enabled,
    )


def dynamic_package(version: str = "1") -> PluginPackage:
    return PluginPackage(
        "dynamic.package",
        version,
        (
            PluginContribution(
                "dynamic", "server", descriptor("dynamic", version=version)
            ),
        ),
    )


def exporting_package() -> PluginPackage:
    return PluginPackage(
        "export.package",
        "1",
        (
            PluginContribution(
                "export",
                "server",
                descriptor("export", specification=SPEC_TOOL_EXPORT_TARGET),
                tool_exports=(
                    ToolExport("echo", "Echo", "echo", object),
                    ToolExport("echo_id", "Echo id", "echo", object, "agent_instance"),
                ),
            ),
        ),
    )


def agent_instance_package() -> PluginPackage:
    return PluginPackage(
        "instance.package",
        "1",
        (
            PluginContribution(
                "instance",
                "agent_instance",
                descriptor("instance", scope="agent", scope_parent="root"),
            ),
        ),
    )


def same_module_package() -> PluginPackage:
    return PluginPackage(
        "dynamic.core",
        "1",
        (
            PluginContribution("one", "server", descriptor("one")),
            PluginContribution("two", "server", descriptor("two")),
        ),
    )


def manager() -> Mock:
    value = Mock()
    value.registry = PluginRegistry()
    value.scope_tree = ScopeTree()
    value.bound = set()
    value.instances = []
    value.target = FakeTarget()

    def ensure_scope(scope_id, *, name=None, parent_id=None):
        if value.scope_tree.get(scope_id) is not None:
            return
        wanted = parent_id if parent_id is not None else ROOT_SCOPE_ID
        if value.scope_tree.get(wanted) is None:
            value.scope_tree.create(wanted, str(wanted), ROOT_SCOPE_ID)
        value.scope_tree.create(scope_id, name or str(scope_id), wanted)

    def ensure_descriptor_scope(descriptor):
        if not descriptor.scope:
            return
        scope_id = ScopeId(descriptor.scope)
        if value.scope_tree.get(scope_id) is None:
            ensure_scope(
                scope_id,
                name=descriptor.scope,
                parent_id=ScopeId(descriptor.scope_parent or str(ROOT_SCOPE_ID)),
            )

    def install(descriptor):
        if value.registry.get(descriptor.name) is None:
            value.registry.add(descriptor)
        ensure_descriptor_scope(descriptor)
        if descriptor.enabled:
            value.bound.add(descriptor.name)

    def bind(name):
        current = value.registry.get(name)
        if current is None:
            raise KeyError(name)
        value.bound.add(name)
        ensure_descriptor_scope(current)

    def unbind(name):
        if name not in value.bound:
            raise KeyError(name)
        value.bound.discard(name)

    def replace(descriptor):
        if value.registry.get(descriptor.name) is not None:
            value.registry.remove(descriptor.name)
        value.registry.add(descriptor)
        ensure_descriptor_scope(descriptor)
        if descriptor.enabled:
            value.bound.add(descriptor.name)
        else:
            value.bound.discard(descriptor.name)

    def uninstall(name):
        if value.registry.get(name) is None:
            raise KeyError(name)
        value.bound.discard(name)

    def instantiate(descriptor, *, scope_id=None, plugin_key=None):
        value.instances.append(descriptor.instance)

    def kill(instance):
        if instance not in value.instances:
            raise KeyError(instance)
        value.instances.remove(instance)

    value.ensure_scope.side_effect = ensure_scope
    value.install_plugin.side_effect = install
    value.bind_plugin.side_effect = bind
    value.unbind_plugin.side_effect = unbind
    value.replace_plugin.side_effect = replace
    value.uninstall_plugin.side_effect = uninstall
    value.instantiate_instance.side_effect = instantiate
    value.kill_instance.side_effect = kill
    value.find_service.return_value = value.target
    return value


class CountingStore(InMemoryRuntimeStateStore):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.saves = 0
        self.fail = fail

    def save(self, snapshot, *, expected_version):
        self.saves += 1
        if self.fail:
            raise OSError("disk full")
        return super().save(snapshot, expected_version=expected_version)


def coordinator(
    runtime: Mock,
    store: CountingStore,
    *,
    packages: tuple[PluginPackage, ...] = (),
) -> RuntimeMutationCoordinator:
    if packages:
        discovery = PluginDiscovery(
            lambda: [
                EntryPoint(item, name=f"ep-{index}")
                for index, item in enumerate(packages)
            ]
        )
    else:
        discovery = PluginDiscovery(lambda: [EntryPoint(dynamic_package())])
    result = RuntimeMutationCoordinator(runtime, store, discovery)
    result.rescan()
    return result


def test_each_successful_mutation_persists_exactly_once() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)

    mutations.install("dynamic.package", "dynamic")
    assert store.saves == 1
    mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))
    assert store.saves == 2
    mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))
    assert store.saves == 3
    mutations.uninstall("dynamic", scope_id=ScopeId("server"))
    assert store.saves == 4


def test_runtime_failure_does_not_persist() -> None:
    runtime = manager()
    runtime.install_plugin.side_effect = RuntimeError("factory failed")
    store = CountingStore()
    mutations = coordinator(runtime, store)

    with pytest.raises(RuntimeError, match="factory failed"):
        mutations.install("dynamic.package", "dynamic")
    assert store.saves == 0


def test_persistence_failure_rolls_back_runtime_install() -> None:
    runtime = manager()
    store = CountingStore(fail=True)
    mutations = coordinator(runtime, store)

    with pytest.raises(OSError, match="disk full"):
        mutations.install("dynamic.package", "dynamic")

    runtime.uninstall_plugin.assert_called_with("dynamic")
    assert runtime.registry.get("dynamic") is None
    assert mutations.registrations() == ()


def test_install_exports_agent_and_agent_instance_adapters() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(exporting_package(),))

    registration = mutations.install("export.package", "export")

    assert registration.plugin_key == "export"
    assert len(runtime.instantiate_instance.call_args_list) == 2
    agent_call = runtime.instantiate_instance.call_args_list[0]
    instance_call = runtime.instantiate_instance.call_args_list[1]
    assert agent_call.kwargs["scope_id"] == ScopeId("agent")
    assert agent_call.args[0].scope_parent == "root"
    assert instance_call.kwargs["scope_id"] == ScopeId("server")


def test_agent_instance_contribution_suffixes_descriptor() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(agent_instance_package(),))

    registration = mutations.install(
        "instance.package", "instance", scope_id=ScopeId("agent:a")
    )

    assert registration.descriptor.name == "instance@agent-a"
    assert registration.descriptor.instance == "instance@agent-a"
    assert registration.scope_id == ScopeId("agent:a")
    assert registration.descriptor.properties["plugin.agent_id"] == "a"


def test_agent_instance_contribution_requires_agent_scope() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(agent_instance_package(),))

    with pytest.raises(RuntimeError, match="agent:<id>"):
        mutations.install("instance.package", "instance")


def test_duplicate_install_is_rejected() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)

    mutations.install("dynamic.package", "dynamic")
    with pytest.raises(RuntimeError, match="already installed"):
        mutations.install("dynamic.package", "dynamic")
    assert store.saves == 1


def test_builtin_packages_cannot_be_dynamically_installed() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)

    with pytest.raises(RuntimeError, match="Built-in plugins"):
        mutations.install("builtin.api", "auth")

    assert store.saves == 0
    assert mutations.registrations() == ()


def test_enable_installs_adapters_and_disable_kills_them() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(exporting_package(),))
    mutations.install("export.package", "export")

    mutations.set_enabled("export", False, scope_id=ScopeId("server"))
    assert runtime.kill_instance.call_count == 2
    assert "disabled" in mutations.registrations()[0].status

    mutations.set_enabled("export", True, scope_id=ScopeId("server"))
    assert runtime.instantiate_instance.call_count == 4
    assert "installed" in mutations.registrations()[0].status


def test_upgrade_replaces_plugin_and_persists() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    mutations._catalog = {"dynamic.package": dynamic_package(version="2")}
    updated = mutations.upgrade("dynamic", scope_id=ScopeId("server"))

    assert updated.package_version == "2"
    assert updated.descriptor.version == "2"
    runtime.replace_plugin.assert_called_once()
    assert store.saves == 2


def test_upgrade_same_version_is_a_noop() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    current = mutations.upgrade("dynamic", scope_id=ScopeId("server"))

    assert current.package_version == "1"
    runtime.replace_plugin.assert_not_called()
    assert store.saves == 1


def test_update_properties_replaces_plugin_and_persists() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    updated = mutations.update_properties(
        "dynamic", {"plugin.value": "new"}, scope_id=ScopeId("server")
    )

    assert updated.descriptor.properties == {"plugin.value": "new"}
    runtime.replace_plugin.assert_called_once_with(updated.descriptor)
    assert store.saves == 2


def test_upgrade_persistence_failure_rolls_back_runtime() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    mutations._catalog = {"dynamic.package": dynamic_package(version="2")}
    store.fail = True
    with pytest.raises(OSError, match="disk full"):
        mutations.upgrade("dynamic", scope_id=ScopeId("server"))

    assert mutations.registrations()[0].package_version == "1"


def test_uninstall_persistence_failure_rolls_back_runtime() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    registration = mutations.install("dynamic.package", "dynamic")

    store.fail = True
    with pytest.raises(OSError, match="disk full"):
        mutations.uninstall("dynamic", scope_id=ScopeId("server"))

    assert runtime.registry.get("dynamic") is not None
    assert mutations.registrations() == (registration,)


def test_unknown_mutation_targets_raise_key_error() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)

    with pytest.raises(KeyError):
        mutations.set_enabled("nope", True, scope_id=ScopeId("server"))
    with pytest.raises(KeyError):
        mutations.upgrade("nope", scope_id=ScopeId("server"))
    with pytest.raises(KeyError):
        mutations.uninstall("nope", scope_id=ScopeId("server"))
    with pytest.raises(KeyError):
        mutations.install("missing.package", "contribution")
    mutations._catalog = {"dynamic.package": dynamic_package()}
    with pytest.raises(KeyError):
        mutations.install("dynamic.package", "missing-contribution")


def test_restore_marks_missing_package_without_blocking_available_plugins() -> None:
    snapshot = RuntimeStateSnapshot(
        1,
        ({"id": "root", "parent_id": None, "name": "root"},),
        (),
    )
    store = CountingStore()
    store.snapshot = snapshot
    runtime = manager()
    mutations = coordinator(runtime, store)

    registration = mutations.install("dynamic.package", "dynamic")
    store.snapshot = RuntimeStateSnapshot(
        store.snapshot.version,
        store.snapshot.scopes,
        (
            registration,
            registration.__class__(
                "missing.package",
                "gone",
                "1",
                ScopeId("server"),
                "gone",
                PluginDescriptor(
                    "gone", "1", "gone.module", "gone-factory", "gone", "gone"
                ),
                True,
                "installed",
            ),
        ),
    )
    restored_runtime = manager()
    restored = RuntimeMutationCoordinator(
        restored_runtime,
        store,
        PluginDiscovery(lambda: [EntryPoint(dynamic_package())]),
    )

    assert restored.restore() == (registration,)
    assert restored.registrations()[1].status == "missing"


def test_restore_marks_upgrade_available_and_failed() -> None:
    failing = PluginPackage(
        "failing.package",
        "1",
        (PluginContribution("fail", "server", descriptor("fail")),),
    )
    snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "server", "parent_id": "root", "name": "server"},
        ),
        (
            PersistedPluginRegistration(
                "dynamic.package",
                "dynamic",
                "1",
                ScopeId("server"),
                "dynamic",
                descriptor("dynamic"),
                True,
                "installed",
            ),
            PersistedPluginRegistration(
                "failing.package",
                "fail",
                "1",
                ScopeId("server"),
                "fail",
                descriptor("fail"),
                True,
                "installed",
            ),
            PersistedPluginRegistration(
                "missing.package",
                "gone",
                "1",
                ScopeId("server"),
                "gone",
                descriptor("gone"),
                True,
                "installed",
            ),
        ),
    )
    store = CountingStore()
    store.snapshot = snapshot
    runtime = manager()

    def install(desc):
        if desc.name == "fail":
            raise RuntimeError("factory failed")
        if runtime.registry.get(desc.name) is None:
            runtime.registry.add(desc)
        runtime.bound.add(desc.name)

    runtime.install_plugin.side_effect = install
    runtime.find_service.return_value = FakeTarget()
    mutations = RuntimeMutationCoordinator(
        runtime,
        store,
        PluginDiscovery(
            lambda: [
                EntryPoint(dynamic_package(version="2"), name="ep-dynamic"),
                EntryPoint(failing, name="ep-failing"),
            ]
        ),
    )

    restored = mutations.restore()

    assert [item.descriptor.name for item in restored] == ["dynamic"]
    statuses = {item.descriptor.name: item.status for item in mutations.registrations()}
    assert statuses["dynamic"] == "upgrade_available"
    assert statuses["fail"] == "failed"
    assert statuses["gone"] == "missing"
    assert store.saves == 1


def test_restore_raises_for_orphaned_persisted_scope() -> None:
    store = CountingStore()
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "agent:a", "parent_id": "agent", "name": "A"},
        ),
        (),
    )
    runtime = manager()
    mutations = RuntimeMutationCoordinator(
        runtime, store, PluginDiscovery(lambda: [])
    )

    with pytest.raises(RuntimeError, match="orphan"):
        mutations.restore()


def test_restore_skips_legacy_and_preexisting_scopes() -> None:
    store = CountingStore()
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "agent", "parent_id": "server", "name": "Agent"},
            {"id": "agent/a", "parent_id": "agent", "name": "A"},
        ),
        (),
    )
    runtime = manager()
    # The fake tree already carries the seeded built-in: agent under root.
    runtime.scope_tree.create(ScopeId("agent"), "Agent", ROOT_SCOPE_ID)
    mutations = RuntimeMutationCoordinator(
        runtime, store, PluginDiscovery(lambda: [])
    )

    assert mutations.restore() == ()

    ids = {scope.id for scope in runtime.scope_tree.snapshot().scopes}
    assert ScopeId("agent/a") not in ids
    assert runtime.scope_tree.get(ScopeId("agent")).parent_id == ROOT_SCOPE_ID


def test_restore_drops_legacy_agent_slash_registrations() -> None:
    store = CountingStore()
    legacy = PersistedPluginRegistration(
        "gone.package",
        "echo",
        "1",
        ScopeId("agent/a"),
        "echo",
        descriptor("echo"),
        True,
        "installed",
    )
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "agent", "parent_id": "root", "name": "Agent"},
            {"id": "agent/a", "parent_id": "agent", "name": "A"},
        ),
        (legacy,),
    )
    runtime = manager()
    runtime.scope_tree.create(ScopeId("agent"), "Agent", ROOT_SCOPE_ID)
    mutations = RuntimeMutationCoordinator(
        runtime, store, PluginDiscovery(lambda: [])
    )

    assert mutations.restore() == ()
    assert mutations.registrations() == ()
    assert store.saves == 1


def test_scopes_returns_the_live_scope_tree_snapshot() -> None:
    runtime = manager()
    runtime.scope_tree.create(ScopeId("agent"), "Agent", ROOT_SCOPE_ID)
    store = CountingStore()
    mutations = coordinator(runtime, store)

    assert {scope.id for scope in mutations.scopes()} == {
        ROOT_SCOPE_ID,
        ScopeId("agent"),
    }


def test_rescan_and_discovered_are_sorted() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(dynamic_package(),))

    assert [item.id for item in mutations.discovered()] == ["dynamic.package"]


def test_set_enabled_noop_when_state_is_unchanged() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    current = mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))

    assert current.enabled is True
    assert store.saves == 1


def test_set_enabled_enable_persistence_failure_rolls_back() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")
    mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))

    store.fail = True
    with pytest.raises(OSError, match="disk full"):
        mutations.set_enabled("dynamic", True, scope_id=ScopeId("server"))

    assert mutations.registrations()[0].enabled is False
    assert runtime.registry.get("dynamic").enabled is False


def test_set_enabled_disable_persistence_failure_rolls_back() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store)
    mutations.install("dynamic.package", "dynamic")

    store.fail = True
    with pytest.raises(OSError, match="disk full"):
        mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))

    assert mutations.registrations()[0].enabled is True
    assert runtime.registry.get("dynamic").enabled is True


def test_upgrade_with_adapters_installs_them() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(exporting_package(),))
    mutations.install("export.package", "export")

    mutations._catalog = {
        "export.package": PluginPackage(
            "export.package",
            "2",
            exporting_package().contributions,
        )
    }
    updated = mutations.upgrade("export", scope_id=ScopeId("server"))

    assert updated.package_version == "2"
    assert runtime.instantiate_instance.call_count == 4


def test_install_export_fails_when_target_service_is_missing() -> None:
    runtime = manager()
    runtime.find_service.return_value = None
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(exporting_package(),))

    with pytest.raises(RuntimeError, match="Tool export target service"):
        mutations.install("export.package", "export")

    assert mutations.registrations() == ()
    assert runtime.registry.get("export") is None


def test_same_name_in_two_scopes_targets_only_the_given_scope() -> None:
    server_reg = PersistedPluginRegistration(
        "dynamic.package", "dynamic", "1", ScopeId("server"), "dynamic",
        descriptor("dynamic"), True, "installed",
    )
    ui_reg = PersistedPluginRegistration(
        "dynamic.package", "dynamic", "1", ScopeId("ui"), "dynamic",
        descriptor("dynamic", scope="ui"), True, "installed",
    )
    store = CountingStore()
    store.snapshot = RuntimeStateSnapshot(
        1,
        (
            {"id": "root", "parent_id": None, "name": "root"},
            {"id": "server", "parent_id": "root", "name": "server"},
            {"id": "ui", "parent_id": "root", "name": "ui"},
        ),
        (server_reg, ui_reg),
    )
    runtime = manager()
    runtime.registry.add(descriptor("dynamic"))
    runtime.bound.add("dynamic")
    mutations = RuntimeMutationCoordinator(runtime, store, PluginDiscovery(lambda: []))

    updated = mutations.set_enabled("dynamic", False, scope_id=ScopeId("server"))

    assert updated.scope_id == ScopeId("server")
    assert mutations.registrations()[0].enabled is False
    assert mutations.registrations()[1].enabled is True

    with pytest.raises(KeyError, match="not found in scope"):
        mutations.set_enabled("dynamic", False, scope_id=ScopeId("agent"))


def test_install_rejects_a_second_registration_sharing_a_module() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(same_module_package(),))

    mutations.install("dynamic.core", "one")

    with pytest.raises(RuntimeMutationError, match="one plugin per module"):
        mutations.install("dynamic.core", "two")


def test_install_allows_same_module_after_uninstall() -> None:
    runtime = manager()
    store = CountingStore()
    mutations = coordinator(runtime, store, packages=(same_module_package(),))

    mutations.install("dynamic.core", "one")
    mutations.uninstall("one", scope_id=ScopeId("server"))
    mutations.install("dynamic.core", "two")
    assert [item.descriptor.name for item in mutations.registrations()] == ["two"]
