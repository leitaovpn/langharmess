"""Transactional orchestration of dynamic plugin runtime mutations."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock

from langharmess_plugin.discovery import DiscoveryResult, PluginDiscovery
from langharmess_plugin.package import PluginContribution, PluginPackage
from langharmess_plugin.plugin_manager import PluginManager
from langharmess_plugin.registry import PluginDescriptor
from langharmess_plugin.state_store import (
    PersistedPluginRegistration,
    RuntimeStateSnapshot,
    RuntimeStateStore,
)
from langharmess_scope import ROOT_SCOPE_ID, ScopeId

TOOL_ADAPTER_MODULE = "langharmess_core.plugins.tools.export_adapter"
TOOL_ADAPTER_FACTORY = "tool-export-adapter-factory"
TOOL_SPECIFICATION = "agent.plugin.tools"
BUILTIN_PACKAGE_PREFIX = "builtin."


class RuntimeMutationError(RuntimeError):
    pass


class RuntimeMutationCoordinator:
    """Makes a runtime change first, then persists its final state exactly once."""

    def __init__(
        self,
        manager: PluginManager,
        store: RuntimeStateStore,
        discovery: PluginDiscovery | None = None,
    ) -> None:
        self.manager = manager
        self.store = store
        self.discovery = discovery if discovery is not None else PluginDiscovery()
        self._lock = RLock()
        loaded = store.load()
        self._version = loaded.version if loaded is not None else 0
        self._loaded_scopes = loaded.scopes if loaded is not None else ()
        self._registrations = list(loaded.plugins) if loaded is not None else []
        self._catalog: dict[str, PluginPackage] = {}
        self._failures: tuple[object, ...] = ()
        self._adapters: dict[str, list[str]] = {}

    def rescan(self) -> DiscoveryResult:
        result = self.discovery.scan()
        self._catalog = {package.id: package for package in result.packages}
        self._failures = result.failures
        return result

    def discovered(self) -> tuple[PluginPackage, ...]:
        return tuple(self._catalog[key] for key in sorted(self._catalog))

    def registrations(self) -> tuple[PersistedPluginRegistration, ...]:
        return tuple(self._registrations)

    def install(
        self,
        package_id: str,
        contribution_id: str,
        *,
        scope_id: ScopeId | None = None,
    ) -> PersistedPluginRegistration:
        with self._lock:
            if package_id.startswith(BUILTIN_PACKAGE_PREFIX):
                raise RuntimeMutationError(
                    "Built-in plugins are managed by server/CLI assembly "
                    "and cannot be installed dynamically"
                )
            package, contribution = self._find(package_id, contribution_id)
            descriptor = self._descriptor(contribution, scope_id)
            if any(item.descriptor.name == descriptor.name for item in self._registrations):
                raise RuntimeMutationError(
                    f"Plugin is already installed: {descriptor.name}"
                )
            self.manager.install_plugin(descriptor)
            registration = PersistedPluginRegistration(
                package.id,
                contribution.id,
                package.version,
                ScopeId(descriptor.scope or str(ROOT_SCOPE_ID)),
                contribution.descriptor.name,
                descriptor,
                descriptor.enabled,
                "installed" if descriptor.enabled else "disabled",
            )
            self._registrations.append(registration)
            try:
                self._install_adapters(registration, contribution)
                self._persist_once()
            except Exception:
                self._kill_adapters(descriptor.name)
                self._registrations.pop()
                self.manager.uninstall_plugin(descriptor.name)
                self.manager.registry.remove(descriptor.name)
                raise
            return registration

    def set_enabled(self, name: str, enabled: bool) -> PersistedPluginRegistration:
        with self._lock:
            index, current = self._registration(name)
            if current.enabled == enabled:
                return current
            if enabled:
                self.manager.bind_plugin(name)
                package, contribution = self._find(
                    current.package_id, current.contribution_id
                )
                self._install_adapters(current, contribution)
            else:
                self._kill_adapters(name)
                self.manager.unbind_plugin(name)
            self.manager.registry.set_enabled(name, enabled)
            updated = replace(
                current,
                enabled=enabled,
                status="installed" if enabled else "disabled",
                descriptor=replace(current.descriptor, enabled=enabled),
            )
            self._registrations[index] = updated
            try:
                self._persist_once()
            except Exception:
                self.manager.registry.set_enabled(name, not enabled)
                if enabled:
                    self._kill_adapters(name)
                    self.manager.unbind_plugin(name)
                else:
                    self.manager.bind_plugin(name)
                    package, contribution = self._find(
                        current.package_id, current.contribution_id
                    )
                    self._install_adapters(current, contribution)
                self._registrations[index] = current
                raise
            return updated

    def upgrade(self, name: str) -> PersistedPluginRegistration:
        with self._lock:
            index, current = self._registration(name)
            package, contribution = self._find(
                current.package_id, current.contribution_id
            )
            if package.version == current.package_version:
                return current
            descriptor = replace(
                self._descriptor(contribution, current.scope_id),
                enabled=current.enabled,
            )
            self._kill_adapters(name)
            self.manager.replace_plugin(descriptor)
            updated = replace(
                current,
                package_version=package.version,
                descriptor=descriptor,
                status="installed" if current.enabled else "disabled",
            )
            self._registrations[index] = updated
            try:
                if updated.enabled:
                    self._install_adapters(updated, contribution)
                self._persist_once()
            except Exception:
                self._kill_adapters(name)
                self.manager.replace_plugin(current.descriptor)
                self._registrations[index] = current
                raise
            return updated

    def uninstall(self, name: str) -> None:
        with self._lock:
            index, current = self._registration(name)
            self._kill_adapters(name)
            self.manager.uninstall_plugin(name)
            self.manager.registry.remove(name)
            self._registrations.pop(index)
            try:
                self._persist_once()
            except Exception:
                self.manager.registry.add(current.descriptor)
                self.manager.install_plugin(current.descriptor)
                package, contribution = self._find(
                    current.package_id, current.contribution_id
                )
                self._install_adapters(current, contribution)
                self._registrations.insert(index, current)
                raise

    def restore(self) -> tuple[PersistedPluginRegistration, ...]:
        """Restore available registrations; missing/broken packages don't block."""
        with self._lock:
            if not self._catalog:
                self.rescan()
            self._restore_scopes()
            changed = False
            restored: list[PersistedPluginRegistration] = []
            for index, registration in enumerate(tuple(self._registrations)):
                package = self._catalog.get(registration.package_id)
                if package is None:
                    updated = replace(registration, status="missing")
                    self._registrations[index] = updated
                    changed |= updated != registration
                    continue
                if package.version != registration.package_version:
                    updated = replace(registration, status="upgrade_available")
                    self._registrations[index] = updated
                    changed |= updated != registration
                    registration = updated
                try:
                    if self.manager.registry.get(registration.descriptor.name) is None:
                        self.manager.install_plugin(registration.descriptor)
                    if registration.enabled:
                        contribution = next(
                            item
                            for item in package.contributions
                            if item.id == registration.contribution_id
                        )
                        self._install_adapters(registration, contribution)
                    restored.append(registration)
                except Exception:
                    updated = replace(registration, status="failed")
                    self._registrations[index] = updated
                    changed |= updated != registration
            if changed:
                self._persist_once()
            return tuple(restored)

    def _find(
        self, package_id: str, contribution_id: str
    ) -> tuple[PluginPackage, PluginContribution]:
        package = self._catalog.get(package_id)
        if package is None:
            raise KeyError(package_id)
        for contribution in package.contributions:
            if contribution.id == contribution_id:
                return package, contribution
        raise KeyError(contribution_id)

    @staticmethod
    def _descriptor(
        contribution: PluginContribution, scope_id: ScopeId | None
    ) -> PluginDescriptor:
        descriptor = contribution.descriptor
        if contribution.target != "agent_instance":
            return descriptor
        if scope_id is None or not str(scope_id).startswith("agent/"):
            raise RuntimeMutationError("agent_instance contribution requires agent/<id>")
        suffix = str(scope_id).replace("/", "-")
        return replace(
            descriptor,
            name=f"{descriptor.name}@{suffix}",
            instance=f"{descriptor.instance}@{suffix}",
            scope=str(scope_id),
            scope_parent="agent",
        )

    def _restore_scopes(self) -> None:
        pending = {
            ScopeId(str(item["id"])): item
            for item in self._loaded_scopes
            if item["id"] != str(ROOT_SCOPE_ID)
        }
        while pending:
            progressed = False
            for scope_id, item in tuple(pending.items()):
                parent = ScopeId(str(item["parent_id"]))
                if self.manager.scope_tree.get(parent) is None:
                    continue
                self.manager.ensure_scope(
                    scope_id,
                    name=str(item["name"]),
                    parent_id=parent,
                )
                pending.pop(scope_id)
                progressed = True
            if not progressed:
                raise RuntimeMutationError("Persisted scope tree contains an orphan")

    def _registration(
        self, name: str
    ) -> tuple[int, PersistedPluginRegistration]:
        for index, registration in enumerate(self._registrations):
            if registration.descriptor.name == name:
                return index, registration
        raise KeyError(name)

    def _install_adapters(
        self,
        registration: PersistedPluginRegistration,
        contribution: PluginContribution,
    ) -> None:
        if not contribution.tool_exports:
            return
        source_scope = registration.scope_id
        target = self.manager.find_service(
            registration.descriptor.specification,
            f"(plugin.scope_id={source_scope})",
        )
        if target is None:
            raise RuntimeMutationError("Tool export target service is unavailable")
        groups: dict[str, list[object]] = {}
        for export in contribution.tool_exports:
            target_scope = (
                str(source_scope)
                if export.target_scope == "agent_instance"
                else "agent"
            )
            groups.setdefault(target_scope, []).append(export)
        created: list[str] = []
        for target_scope, exports in groups.items():
            suffix = target_scope.replace("/", "-")
            instance_name = f"tool-export@{registration.descriptor.name}@{suffix}"
            descriptor = PluginDescriptor(
                name=instance_name,
                version=registration.package_version,
                module=TOOL_ADAPTER_MODULE,
                factory=TOOL_ADAPTER_FACTORY,
                instance=instance_name,
                specification=TOOL_SPECIFICATION,
                properties={
                    "plugin.tool_export.target": target,
                    "plugin.tool_export.exports": exports,
                },
                scope=target_scope,
                scope_parent="agent" if target_scope.startswith("agent/") else "server",
            )
            self.manager.instantiate_instance(
                descriptor,
                scope_id=ScopeId(target_scope),
                plugin_key=f"tool-export:{registration.package_id}:{contribution.id}",
            )
            created.append(instance_name)
        self._adapters[registration.descriptor.name] = created

    def _kill_adapters(self, name: str) -> None:
        for instance_name in reversed(self._adapters.pop(name, [])):
            self.manager.kill_instance(instance_name)

    def _persist_once(self) -> None:
        scopes = self.manager.scope_tree.snapshot().scopes
        snapshot = RuntimeStateSnapshot(
            self._version,
            tuple(
                {
                    "id": str(scope.id),
                    "parent_id": (
                        str(scope.parent_id) if scope.parent_id is not None else None
                    ),
                    "name": scope.name,
                }
                for scope in scopes
            ),
            tuple(self._registrations),
        )
        self._version = self.store.save(snapshot, expected_version=self._version)
