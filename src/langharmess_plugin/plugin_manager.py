"""Lifecycle manager for Pelix/iPOPO plugin bundles."""

from __future__ import annotations

from typing import Any

from pelix import ldapfilter
from pelix.framework import BundleContext, Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import SERVICE_IPOPO

from langharmess_plugin.config_store import apply_overrides
from langharmess_plugin.contracts import (
    PluginRegistrar,
    ScopedPluginRegistrar,
)
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.scope_policy import PluginScopePolicy
from langharmess_plugin.validation import (
    ContractViolationError,
    contract_for,
    validate,
)
from langharmess_scope import ROOT_SCOPE_ID, ScopeId, ScopeTree

FILTERS_PROPERTY = "requires.filters"
SERVICE_RANKING = "service.ranking"
SCOPE_RANKING_STRIDE = 1_000_000
PLUGIN_SCOPE_ID = "plugin.scope_id"
PLUGIN_SCOPE_CHAIN = "plugin.scope_chain"
PLUGIN_KEY = "plugin.key"
PLUGIN_RANKING = "plugin.ranking"


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
    """Installs, binds, unbinds, and uninstalls plugin components."""

    def __init__(
        self, registry: PluginRegistry, *, scope_tree: ScopeTree | None = None
    ) -> None:
        self.registry = registry
        self.scope_tree = scope_tree if scope_tree is not None else ScopeTree()
        self._scope_policy = PluginScopePolicy(self.scope_tree)
        self._framework: Framework | None = None
        self._context: BundleContext | None = None
        self._ipopo: Any = None
        self._bundles: dict[str, Any] = {}
        self._bound: set[str] = set()
        self._modules: set[str] = set()
        self._scoped: dict[str, PluginDescriptor] = {}
        self._instance_scopes: dict[str, ScopeId] = {}
        self._scope_keys: dict[tuple[ScopeId, str], str] = {}
        self._baselines: dict[str, PluginDescriptor] = {}
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
        self._registration = self._context.register_service(
            PluginRegistrar, self, {}
        )
        self._scope_registration = self._context.register_service(
            ScopedPluginRegistrar, self, {}
        )

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
        self._bound.clear()
        self._modules.clear()
        self._scoped.clear()
        self._instance_scopes.clear()
        self._scope_keys.clear()
        self._baselines.clear()

    def install_plugin(self, descriptor: PluginDescriptor) -> None:
        if not self.started or self._context is None or self._ipopo is None:
            raise RuntimeError("PluginManager is not started")
        if descriptor.name in self._bundles:
            raise ValueError(f"Plugin {descriptor.name!r} is already installed")
        if self.registry.get(descriptor.name) is None:
            self.registry.add(descriptor)
        scope_id = self._ensure_descriptor_scope(descriptor)

        bundle = self._context.install_bundle(descriptor.module)
        bundle.start()
        self._bundles[descriptor.name] = bundle
        # The first descriptor installed is the baseline runtime config applies
        # overrides to; runtime replacements must not move it.
        self._baselines.setdefault(descriptor.name, descriptor)
        self._modules.add(descriptor.module)
        if descriptor.enabled:
            if scope_id is None:
                self._instantiate(descriptor)
            else:
                self.instantiate_instance(
                    descriptor, scope_id=scope_id, plugin_key=descriptor.name
                )
                self._scoped.pop(descriptor.instance)
                self._bound.add(descriptor.name)

    def uninstall_plugin(self, name: str) -> None:
        if name not in self._bundles:
            raise KeyError(name)
        if name in self._bound:
            self._unbind(name)
        bundle = self._bundles.pop(name)
        bundle.stop()
        bundle.uninstall()
        self._baselines.pop(name, None)
        descriptor = self.registry.get(name)
        if descriptor is not None and not self._module_in_use(descriptor.module):
            self._modules.discard(descriptor.module)

    def _module_in_use(self, module: str) -> bool:
        for name in self._bundles:
            other = self.registry.get(name)
            if other is not None and other.module == module:
                return True
        return False

    def replace_plugin(self, descriptor: PluginDescriptor) -> None:
        """Replace a named runtime plugin descriptor and component."""
        baseline = self._baselines.get(descriptor.name)
        if descriptor.name in self._bundles:
            self.uninstall_plugin(descriptor.name)
        if self.registry.get(descriptor.name) is not None:
            self.registry.remove(descriptor.name)
        self.registry.add(descriptor)
        self.install_plugin(descriptor)
        if baseline is not None:
            self._baselines[descriptor.name] = baseline

    def ensure_plugin(self, descriptor: PluginDescriptor) -> None:
        """Install a runtime plugin, replacing it only when configuration changes."""
        current = self.registry.get(descriptor.name)
        if current == descriptor and descriptor.name in self._bundles:
            return
        self.replace_plugin(descriptor)

    def bind_plugin(self, name: str) -> None:
        if name not in self._bundles:
            raise KeyError(name)
        descriptor = self._get_descriptor(name)
        scope_id = self._ensure_descriptor_scope(descriptor)
        if scope_id is None:
            self._instantiate(descriptor)
        else:
            self.instantiate_instance(
                descriptor, scope_id=scope_id, plugin_key=descriptor.name
            )
            self._scoped.pop(descriptor.instance)
            self._bound.add(descriptor.name)

    def unbind_plugin(self, name: str) -> None:
        if name not in self._bundles:
            raise KeyError(name)
        self._unbind(name)

    def instantiate_instance(
        self,
        descriptor: PluginDescriptor,
        *,
        scope_id: ScopeId | None = None,
        plugin_key: str | None = None,
    ) -> None:
        """Instantiate a scoped component from an already installed bundle."""
        if not self.started or self._ipopo is None:
            raise RuntimeError("PluginManager is not started")
        if descriptor.module not in self._modules:
            raise ValueError(f"Bundle {descriptor.module!r} is not installed")
        if descriptor.instance in self._scoped:
            raise ValueError(f"Instance {descriptor.instance!r} is already instantiated")
        if scope_id is None:
            scope_id = self._ensure_descriptor_scope(descriptor)
        properties = dict(descriptor.properties)
        key = plugin_key or descriptor.name.split("@", 1)[0]
        if scope_id is not None:
            self.scope_tree.require(scope_id)
            registration_key = (scope_id, key)
            if registration_key in self._scope_keys:
                raise ValueError(
                    f"Plugin {key!r} is already registered in scope {scope_id!r}"
                )
            properties[PLUGIN_SCOPE_ID] = str(scope_id)
            properties[PLUGIN_SCOPE_CHAIN] = [
                str(item) for item in self._scope_policy.visible_scopes(scope_id)
            ]
            properties[PLUGIN_KEY] = key
            properties[PLUGIN_RANKING] = descriptor.ranking
            properties[SERVICE_RANKING] = (
                self.scope_tree.depth(scope_id) * SCOPE_RANKING_STRIDE
                + descriptor.ranking
            )
        _validate_filters(properties)
        instance = self._ipopo.instantiate(
            descriptor.factory,
            descriptor.instance,
            properties or None,
        )
        if scope_id is not None:
            # The attributes make scope metadata available during the initial
            # validation of consumers. iPOPO does not invoke BindField callbacks
            # for dependencies that were already present before instantiation.
            setattr(instance, "_plugin_scope_id", str(scope_id))
            setattr(instance, "_plugin_key", key)
            setattr(instance, "_plugin_ranking", descriptor.ranking)
        protocol = contract_for(descriptor.specification)
        if protocol is not None:
            violations = validate(instance, protocol)
            if violations:
                self._ipopo.kill(descriptor.instance)
                raise ContractViolationError(
                    plugin=descriptor.name,
                    specification=descriptor.specification,
                    protocol=protocol.__name__,
                    violations=violations,
                )
        self._scoped[descriptor.instance] = descriptor
        if scope_id is not None:
            self._instance_scopes[descriptor.instance] = scope_id
            self._scope_keys[(scope_id, key)] = descriptor.instance

    def kill_instance(self, instance: str) -> None:
        """Kill a scoped instance created by ``instantiate_instance``."""
        if instance not in self._scoped:
            raise KeyError(instance)
        self._ipopo.kill(instance)
        self._scoped.pop(instance)
        scope_id = self._instance_scopes.pop(instance, None)
        if scope_id is not None:
            for registration_key, registered_instance in tuple(self._scope_keys.items()):
                if registered_instance == instance:
                    self._scope_keys.pop(registration_key)

    def scoped_instances(self) -> dict[str, PluginDescriptor]:
        return dict(self._scoped)

    def ensure_scope(
        self,
        scope_id: ScopeId,
        *,
        name: str,
        parent_id: ScopeId | None = None,
    ) -> None:
        existing = self.scope_tree.get(scope_id)
        wanted_parent = parent_id if parent_id is not None else ROOT_SCOPE_ID
        if existing is None:
            self.scope_tree.create(scope_id, name, wanted_parent)
            return
        if existing.parent_id != wanted_parent:
            raise ValueError(f"Scope {scope_id!r} already has a different parent")

    def remove_scope(self, scope_id: ScopeId, *, recursive: bool = False) -> None:
        targets = {scope_id}
        if recursive:
            targets.update(item.id for item in self.scope_tree.descendants(scope_id))
        for instance, instance_scope in reversed(tuple(self._instance_scopes.items())):
            if instance_scope in targets:
                self.kill_instance(instance)
        self.scope_tree.remove(scope_id, recursive=recursive)

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

    def apply_config(
        self, overrides: dict[str, dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Apply stored overrides; hot plugins swap now, the rest need a restart."""
        unknown = [name for name in overrides if self.registry.get(name) is None]
        if unknown:
            raise ValueError(f"Unknown plugin: {sorted(unknown)[0]}")
        applied: list[str] = []
        restart_required: list[str] = []
        # Recompute from the baseline so removing an override reverts the plugin.
        for name in list(self._bundles):
            baseline = self._baselines.get(name)
            if baseline is None:
                continue
            effective = apply_overrides(baseline, overrides.get(name, {}))
            if effective == self.registry.get(name):
                continue
            if effective.swap_policy == "hot":
                self.ensure_plugin(effective)
                applied.append(name)
            else:
                restart_required.append(name)
        return {"applied": applied, "restart_required": restart_required}

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
        """Return every service matching a scoped visibility filter."""
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        references: Any = self._context.get_all_service_references(
            specification, filter
        ) or []
        return [self._context.get_service(reference) for reference in references]

    def installed_modules(self) -> set[str]:
        return set(self._modules)

    def installed_names(self) -> set[str]:
        return set(self._bundles)

    def get_service(self, specification: str) -> Any | None:
        if self._context is None:
            raise RuntimeError("PluginManager is not started")
        reference: Any = self._context.get_service_reference(specification)
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

    def _get_descriptor(self, name: str) -> PluginDescriptor:
        descriptor = self.registry.get(name)
        if descriptor is None:
            raise KeyError(name)
        return descriptor

    def _ensure_descriptor_scope(
        self, descriptor: PluginDescriptor
    ) -> ScopeId | None:
        if descriptor.scope is None:
            return None
        scope_id = ScopeId(descriptor.scope)
        if self.scope_tree.get(scope_id) is not None:
            return scope_id
        parent_id = (
            ScopeId(descriptor.scope_parent)
            if descriptor.scope_parent is not None
            else ROOT_SCOPE_ID
        )
        if self.scope_tree.get(parent_id) is None:
            self.scope_tree.create(parent_id, str(parent_id), ROOT_SCOPE_ID)
        self.scope_tree.create(scope_id, descriptor.scope, parent_id)
        return scope_id

    def _instantiate(self, descriptor: PluginDescriptor) -> None:
        if descriptor.name in self._bound:
            raise ValueError(f"Plugin {descriptor.name!r} is already bound")
        instance = self._ipopo.instantiate(
            descriptor.factory,
            descriptor.instance,
            dict(descriptor.properties) or None,
        )
        protocol = contract_for(descriptor.specification)
        if protocol is not None:
            violations = validate(instance, protocol)
            if violations:
                self._ipopo.kill(descriptor.instance)
                raise ContractViolationError(
                    plugin=descriptor.name,
                    specification=descriptor.specification,
                    protocol=protocol.__name__,
                    violations=violations,
                )
        self._bound.add(descriptor.name)

    def _unbind(self, name: str) -> None:
        if name not in self._bound:
            raise ValueError(f"Plugin {name!r} is not bound")
        descriptor = self._get_descriptor(name)
        self._ipopo.kill(descriptor.instance)
        self._bound.remove(name)
        scope_id = self._instance_scopes.pop(descriptor.instance, None)
        if scope_id is not None:
            self._scope_keys.pop((scope_id, descriptor.name), None)
