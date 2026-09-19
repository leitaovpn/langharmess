"""Lifecycle manager for Pelix/iPOPO plugin bundles."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from pelix import ldapfilter
from pelix.framework import BundleContext, Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import SERVICE_IPOPO

from langharness_plugin.contracts import PluginRegistrar, ScopedPluginRegistrar
from langharness_plugin.discovery import _installed_entry_points, descriptor_discovery
from langharness_plugin.errors import (
    InstanceNotFoundError,
    InstanceStateError,
    PluginAlreadyInstalledError,
    PluginHasInstancesError,
    PluginIdentityConflictError,
    PluginNotFoundError,
    ScopeHasChildrenError,
    ScopeHasInstancesError,
)
from langharness_plugin.registry import (
    DefinitionStatus,
    DiscoverySnapshot,
    InstanceStatus,
    PluginDefinitionSnapshot,
    PluginDescriptor,
    PluginInstanceRecord,
    PluginInstanceSnapshot,
    PluginRegistry,
    validate_descriptor,
)
from langharness_plugin.scope_const import (
    BUILTIN_SCOPES,
    PLUGIN_KEY,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_SCOPE_ID,
)
from langharness_plugin.scope_policy import PluginScopePolicy
from langharness_plugin.scoped_dependencies import scoped_fields_from_module
from langharness_plugin.state_store import (
    DescriptorSource,
    HistoryEntry,
    PersistedDescriptorRecord,
    PersistedPluginRegistration,
    PluginHistoryStore,
    RuntimeStateSnapshot,
    RuntimeStateStore,
)
from langharness_plugin.validation import ContractViolationError, contract_for, validate
from langharness_scope import ROOT_SCOPE_ID, Scope, ScopeId, ScopeTree

LOGGER = logging.getLogger("langharness.plugin_manager")

FILTERS_PROPERTY = "requires.filters"
SERVICE_RANKING = "service.ranking"
SCOPE_RANKING_STRIDE = 1_000_000
PLUGIN_RANKING = "plugin.ranking"
PLUGIN_INSTANCE_ID = "plugin.instance_id"

_RUNTIME_KEYS = (
    PLUGIN_SCOPE_ID,
    PLUGIN_SCOPE_CHAIN,
    PLUGIN_KEY,
    PLUGIN_INSTANCE_ID,
    PLUGIN_RANKING,
    SERVICE_RANKING,
)


def _validate_filters(properties: dict[str, Any]) -> None:
    """Reject malformed requires.filters: iPOPO silently ignores them."""
    filters = properties.get(FILTERS_PROPERTY)
    if filters is None:
        return
    if not isinstance(filters, dict):
        raise ValueError(f"{FILTERS_PROPERTY} must be a mapping of field to filter")
    for field, value in filters.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid filter for {field}: {value!r}")
        try:
            ldapfilter.get_ldap_filter(value)
        except ValueError as exc:
            raise ValueError(f"Invalid filter for {field}: {value!r}") from exc


class PluginManager:
    """Discovers, installs, instantiates, and persists plugin components."""

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        *,
        scope_tree: ScopeTree | None = None,
        discovery: Callable[[], Iterable[Any]] | None = None,
    ) -> None:
        self.registry = registry if registry is not None else PluginRegistry()
        self.scope_tree = scope_tree if scope_tree is not None else ScopeTree()
        self._scope_policy = PluginScopePolicy(self.scope_tree)
        self._discovery_loader = discovery or _installed_entry_points
        self._lock = RLock()
        self._framework: Framework | None = None
        self._context: BundleContext | None = None
        self._ipopo: Any = None
        self._discovered: dict[tuple[str, str], PluginDescriptor] = {}
        self._plugins: dict[tuple[str, str], PluginDefinitionSnapshot] = {}
        self._bundles: dict[str, Any] = {}
        self._module_refs: dict[str, set[tuple[str, str]]] = {}
        self._instances: dict[str, PluginInstanceSnapshot] = {}
        self._registration_instances: dict[tuple[str, str, ScopeId], set[str]] = {}
        self._sources: dict[tuple[str, str], DescriptorSource] = {}
        self._provenance: dict[str, PersistedPluginRegistration] = {}
        self._user_properties: dict[str, dict[str, Any]] = {}
        self._state_store: RuntimeStateStore | None = None
        self._history: PluginHistoryStore | None = None
        self._state_version = 0
        self._registration: Any = None
        self._scope_registration: Any = None
        self._dynamic_registration: Any = None

    @property
    def started(self) -> bool:
        return self._framework is not None

    def start(self) -> None:
        if self.started:
            raise RuntimeError("PluginManager is already started")
        self._framework = create_framework(["pelix.ipopo.core"])
        self._framework.start()
        self._context = self._framework.get_bundle_context()
        ipopo_reference: Any = self._context.get_service_reference(SERVICE_IPOPO)
        assert ipopo_reference is not None
        self._ipopo = self._context.get_service(ipopo_reference)
        self._registration = self._context.register_service(PluginRegistrar, self, {})
        self._scope_registration = self._context.register_service(
            ScopedPluginRegistrar, self, {}
        )
        try:
            self._seed_builtin_scopes()
        except Exception:
            self.stop()
            raise

    def _seed_builtin_scopes(self) -> None:
        for scope_id, name, parent_id in BUILTIN_SCOPES:
            self.add_scope(scope_id, name=name, parent_id=parent_id)

    def stop(self) -> None:
        if self._framework is None:
            return
        FrameworkFactory.delete_framework(self._framework)
        self._framework = None
        self._context = None
        self._ipopo = None
        self._registration = None
        self._scope_registration = None
        self._dynamic_registration = None
        self._bundles.clear()
        self._module_refs.clear()
        self._instances.clear()
        self._registration_instances.clear()
        self._plugins.clear()
        self._discovered.clear()
        self._provenance.clear()
        self._user_properties.clear()

    def _require_started(self) -> None:
        if not self.started or self._context is None or self._ipopo is None:
            raise RuntimeError("PluginManager is not started")

    # ------------------------------------------------------------------ discovery

    def discover(self) -> DiscoverySnapshot:
        self._require_started()
        descriptors, warnings = descriptor_discovery(self._discovery_loader)
        self._discovered = descriptors
        return DiscoverySnapshot(
            tuple(
                sorted(descriptors.values(), key=lambda d: (d.module, d.factory))
            ),
            warnings,
            datetime.now(UTC),
        )

    # --------------------------------------------------------------------- scopes

    def list_scope(self) -> tuple[Scope, ...]:
        return self.scope_tree.snapshot().scopes

    def add_scope(
        self,
        scope_id: ScopeId,
        *,
        name: str,
        parent_id: ScopeId | None = None,
    ) -> Scope:
        wanted_parent = parent_id if parent_id is not None else ROOT_SCOPE_ID
        existing = self.scope_tree.get(scope_id)
        if existing is None:
            return self.scope_tree.create(scope_id, name, wanted_parent)
        if existing.parent_id != wanted_parent:
            raise ValueError(f"Scope {scope_id!r} already has a different parent")
        return existing

    def remove_scope(self, scope_id: ScopeId, *, recursive: bool = False) -> None:
        with self._lock:
            targets = {scope_id}
            if recursive:
                targets.update(
                    item.id for item in self.scope_tree.descendants(scope_id)
                )
            affected = [
                instance
                for instance in self._instances.values()
                if instance.scope_id in targets
            ]
            if not recursive:
                children = self.scope_tree.children(scope_id)
                if children:
                    raise ScopeHasChildrenError(
                        f"Scope {scope_id!r} has child scopes: "
                        f"{[str(item.id) for item in children]}"
                    )
                if affected:
                    raise ScopeHasInstancesError(
                        f"Scope {scope_id!r} has plugin instances"
                    )
            for instance in reversed(affected):
                self._remove_instance_record(instance.instance)
            self.scope_tree.remove(scope_id, recursive=recursive)
            self._persist_state()

    def _remove_instance_record(self, instance: str) -> None:
        snapshot = self._instances.get(instance)
        if snapshot is None:
            return
        if snapshot.status == "active":
            self._ipopo.kill(instance)
        self._instances.pop(instance, None)
        self._user_properties.pop(instance, None)
        self._registration_instances.get(
            (snapshot.module, snapshot.factory, snapshot.scope_id), set()
        ).discard(instance)

    # ------------------------------------------------------------ service helpers

    def scope_filter(self, scope_id: ScopeId) -> str:
        return self._scope_policy.visibility_filter(scope_id)

    def register_runtime_service(self, specification: type[Any], service: Any) -> None:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        if self._dynamic_registration is not None:
            raise RuntimeError("Dynamic plugin manager is already registered")
        self._dynamic_registration = self._context.register_service(
            specification,
            service,
            {PLUGIN_SCOPE_ID: str(ROOT_SCOPE_ID), PLUGIN_KEY: "dynamic-plugin-manager"},
        )

    def installed_modules(self) -> set[str]:
        return set(self._bundles)

    def find_service(
        self, specification: str, filter: str | None = None
    ) -> Any | None:
        """Return the highest-ranked service matching specification and filter."""
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        references: Any = self._context.get_all_service_references(
            specification, filter
        ) or []
        if not references:
            return None
        reference = max(
            references,
            key=lambda item: int(item.get_property(SERVICE_RANKING) or 0),
        )
        return self._context.get_service(reference)

    def find_services(
        self, specification: str, filter: str | None = None
    ) -> list[Any]:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        references: Any = self._context.get_all_service_references(
            specification, filter
        ) or []
        return [self._context.get_service(reference) for reference in references]

    def get_service(self, specification: str, filter: str | None = None) -> Any | None:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        reference: Any = self._context.get_service_reference(specification, filter)
        if reference is None:
            return None
        return self._context.get_service(reference)

    def get_services(self, specification: str) -> list[Any]:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        references: Any = self._context.get_all_service_references(specification) or []
        return [self._context.get_service(reference) for reference in references]

    def service_properties(self, specification: str) -> list[dict[str, Any]]:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        references: Any = self._context.get_all_service_references(specification) or []
        return [dict(reference.get_properties()) for reference in references]

    def apply_config(
        self, overrides: dict[str, dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Placeholder until the instance update path lands (Task 9/13)."""
        return {"applied": [], "restart_required": []}

    # ------------------------------------------------------------- persistence
    # bind_state/restore/_persist_state/_record_history land in a later task.

    def _persist_state(self) -> None:
        if self._state_store is None:
            return

    def _record_history(
        self,
        action: str,
        *,
        factory: str | None = None,
        module: str | None = None,
        scope_id: str | None = None,
        instance: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self._history is None:
            return
