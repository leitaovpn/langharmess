"""Plugin descriptor and JSON-backed registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SWAP_POLICIES = ("hot", "restart")


@dataclass
class PluginDescriptor:
    """Declarative description of one installable plugin."""

    name: str
    version: str
    module: str
    factory: str
    instance: str
    specification: str
    enabled: bool = True
    ranking: int = 0
    properties: dict[str, Any] = field(default_factory=dict)
    swap_policy: str = "restart"
    scope: str | None = None
    scope_parent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "module": self.module,
            "factory": self.factory,
            "instance": self.instance,
            "specification": self.specification,
            "enabled": self.enabled,
            "ranking": self.ranking,
            "properties": self.properties,
            "swap_policy": self.swap_policy,
            "scope": self.scope,
            "scope_parent": self.scope_parent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginDescriptor:
        allowed = {
            "name",
            "version",
            "module",
            "factory",
            "instance",
            "specification",
            "enabled",
            "ranking",
            "properties",
            "swap_policy",
            "scope",
            "scope_parent",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"Unknown descriptor fields: {sorted(unknown)}")

        required = {
            "name",
            "version",
            "module",
            "factory",
            "instance",
            "specification",
        }
        missing = required - set(data)
        if missing:
            raise ValueError(f"Missing descriptor fields: {sorted(missing)}")

        return cls(
            name=data["name"],
            version=data["version"],
            module=data["module"],
            factory=data["factory"],
            instance=data["instance"],
            specification=data["specification"],
            enabled=data.get("enabled", True),
            ranking=data.get("ranking", 0),
            properties=data.get("properties", {}),
            swap_policy=data.get("swap_policy", "restart"),
            scope=data.get("scope"),
            scope_parent=data.get("scope_parent"),
        )


class PluginRegistry:
    """In-memory registry with JSON persistence."""

    def __init__(self, descriptors: list[PluginDescriptor] | tuple[PluginDescriptor, ...] = ()):
        self._descriptors: dict[str, PluginDescriptor] = {}
        for descriptor in descriptors:
            self.add(descriptor)

    def add(self, descriptor: PluginDescriptor) -> None:
        if descriptor.name in self._descriptors:
            raise ValueError(f"Plugin {descriptor.name!r} is already registered")
        for existing in self._descriptors.values():
            if existing.instance == descriptor.instance:
                raise ValueError(
                    f"Plugin instance {descriptor.instance!r} is already registered"
                )
        self._validate(descriptor)
        self._descriptors[descriptor.name] = descriptor

    def get(self, name: str) -> PluginDescriptor | None:
        return self._descriptors.get(name)

    def list(self) -> list[PluginDescriptor]:
        return [self._descriptors[name] for name in sorted(self._descriptors)]

    def remove(self, name: str) -> PluginDescriptor:
        if name not in self._descriptors:
            raise KeyError(name)
        return self._descriptors.pop(name)

    def set_enabled(self, name: str, enabled: bool) -> None:
        descriptor = self._descriptors.get(name)
        if descriptor is None:
            raise KeyError(name)
        descriptor.enabled = enabled

    def save(self, path: Path) -> None:
        data = {
            "version": 1,
            "plugins": [descriptor.to_dict() for descriptor in self.list()],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> PluginRegistry:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != 1:
            raise ValueError("Unsupported plugin registry version")
        descriptors = [
            PluginDescriptor.from_dict(item) for item in raw.get("plugins", [])
        ]
        return cls(descriptors)

    @staticmethod
    def _validate(descriptor: PluginDescriptor) -> None:
        required_text = (
            descriptor.name,
            descriptor.version,
            descriptor.module,
            descriptor.factory,
            descriptor.instance,
            descriptor.specification,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required_text):
            raise ValueError("Plugin descriptor text fields must be non-empty strings")
        if not isinstance(descriptor.enabled, bool):
            raise ValueError("Plugin descriptor 'enabled' must be a bool")
        if not isinstance(descriptor.ranking, int):
            raise ValueError("Plugin descriptor 'ranking' must be an int")
        if descriptor.swap_policy not in SWAP_POLICIES:
            raise ValueError(
                f"Plugin descriptor 'swap_policy' must be one of {SWAP_POLICIES}"
            )
        if descriptor.scope is not None and not descriptor.scope.strip():
            raise ValueError("Plugin descriptor 'scope' must be a non-empty string")
        if descriptor.scope_parent is not None and not descriptor.scope_parent.strip():
            raise ValueError(
                "Plugin descriptor 'scope_parent' must be a non-empty string"
            )
        if descriptor.scope == "root" and descriptor.scope_parent is not None:
            raise ValueError("The root plugin scope cannot have a parent")
        if descriptor.scope not in {None, "root"} and descriptor.scope_parent is None:
            raise ValueError("A non-root plugin scope requires 'scope_parent'")
