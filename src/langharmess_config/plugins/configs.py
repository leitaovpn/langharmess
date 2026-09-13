"""Aggregate all registered configuration providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Provides, Requires

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS


@ComponentFactory("configs-plugin-factory")
@Provides(SPEC_CONFIGS)
@Requires("_providers", SPEC_CONFIG_PROVIDER, aggregate=True, optional=True)
class ConfigsPlugin:
    def __init__(self) -> None:
        self._providers: list[Any] = []

    def _merged(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for provider in self._providers or []:
            self._merge_into(merged, provider.get_config())
        return merged

    def _merge_into(self, target: dict[str, Any], source: Mapping[str, Any]) -> None:
        for key, value in source.items():
            current = target.get(key)
            if isinstance(current, dict) and isinstance(value, Mapping):
                self._merge_into(current, value)
            elif isinstance(value, Mapping):
                target[key] = dict(value)
            else:
                target[key] = value

    def get(
        self, section: str, key: str, fallback: str | None = None
    ) -> str | None:
        value = self.get_section(section).get(key)
        return value if isinstance(value, str) else fallback

    def get_section(self, section: str) -> dict[str, Any]:
        merged = self._merged()
        value: Any = merged.get(section)
        if value is None:
            value = merged
            for part in section.split("."):
                if not isinstance(value, Mapping):
                    return {}
                value = value.get(part)
        if not isinstance(value, Mapping):
            return {}
        defaults = merged.get("DEFAULT", {})
        return {
            **(dict(defaults) if isinstance(defaults, Mapping) else {}),
            **dict(value),
        }

    def get_provider(self, name: str) -> dict[str, Any]:
        return self.get_section(f"providers.{name}")

    def list_providers(self) -> list[str]:
        providers = self._merged().get("providers", {})
        if not isinstance(providers, Mapping):
            return []
        return sorted(
            str(name) for name, value in providers.items() if isinstance(value, Mapping)
        )
