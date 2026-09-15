"""Lifecycle manager for Pelix/iPOPO plugin bundles."""

from __future__ import annotations

from typing import Any

from pelix.framework import BundleContext, Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import SERVICE_IPOPO

from langharmess_plugin.contracts import PluginRegistrar
from langharmess_plugin.registry import PluginDescriptor, PluginRegistry
from langharmess_plugin.validation import (
    ContractViolationError,
    contract_for,
    validate,
)


class PluginManager:
    """Installs, binds, unbinds, and uninstalls plugin components."""

    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self._framework: Framework | None = None
        self._context: BundleContext | None = None
        self._ipopo: Any = None
        self._bundles: dict[str, Any] = {}
        self._bound: set[str] = set()
        self._modules: set[str] = set()
        self._scoped: dict[str, PluginDescriptor] = {}
        self._registration: Any = None

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

    def stop(self) -> None:
        if self._framework is None:
            return
        FrameworkFactory.delete_framework(self._framework)
        self._framework = None
        self._context = None
        self._ipopo = None
        self._registration = None
        self._bundles.clear()
        self._bound.clear()
        self._modules.clear()
        self._scoped.clear()

    def install_plugin(self, descriptor: PluginDescriptor) -> None:
        if not self.started or self._context is None or self._ipopo is None:
            raise RuntimeError("PluginManager is not started")
        if descriptor.name in self._bundles:
            raise ValueError(f"Plugin {descriptor.name!r} is already installed")
        if self.registry.get(descriptor.name) is None:
            self.registry.add(descriptor)

        bundle = self._context.install_bundle(descriptor.module)
        bundle.start()
        self._bundles[descriptor.name] = bundle
        self._modules.add(descriptor.module)
        if descriptor.enabled:
            self._instantiate(descriptor)

    def uninstall_plugin(self, name: str) -> None:
        if name not in self._bundles:
            raise KeyError(name)
        if name in self._bound:
            self._unbind(name)
        bundle = self._bundles.pop(name)
        bundle.stop()
        bundle.uninstall()
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
        if descriptor.name in self._bundles:
            self.uninstall_plugin(descriptor.name)
        if self.registry.get(descriptor.name) is not None:
            self.registry.remove(descriptor.name)
        self.registry.add(descriptor)
        self.install_plugin(descriptor)

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
        self._instantiate(descriptor)

    def unbind_plugin(self, name: str) -> None:
        if name not in self._bundles:
            raise KeyError(name)
        self._unbind(name)

    def instantiate_instance(self, descriptor: PluginDescriptor) -> None:
        """Instantiate a scoped component from an already installed bundle."""
        if not self.started or self._ipopo is None:
            raise RuntimeError("PluginManager is not started")
        if descriptor.module not in self._modules:
            raise ValueError(f"Bundle {descriptor.module!r} is not installed")
        if descriptor.instance in self._scoped:
            raise ValueError(f"Instance {descriptor.instance!r} is already instantiated")
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
        self._scoped[descriptor.instance] = descriptor

    def kill_instance(self, instance: str) -> None:
        """Kill a scoped instance created by ``instantiate_instance``."""
        if instance not in self._scoped:
            raise KeyError(instance)
        self._ipopo.kill(instance)
        self._scoped.pop(instance)

    def scoped_instances(self) -> dict[str, PluginDescriptor]:
        return dict(self._scoped)

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
