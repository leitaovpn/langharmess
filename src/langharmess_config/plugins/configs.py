"""Aggregate all registered configuration providers."""

from __future__ import annotations

from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Provides, Requires

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS


@ComponentFactory("configs-plugin-factory")
@Provides(SPEC_CONFIGS)
@Requires("_providers", SPEC_CONFIG_PROVIDER, aggregate=True, optional=True)
class ConfigsPlugin:
    def __init__(self) -> None:
        self._providers: list[Any] = []

    def _merged(self) -> dict[str, dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        for provider in self._providers or []:
            for section, values in provider.get_config().items():
                merged.setdefault(section, {}).update(values)
        return merged

    def get(
        self, section: str, key: str, fallback: str | None = None
    ) -> str | None:
        return self._merged().get(section, {}).get(key, fallback)

    def get_section(self, section: str) -> dict[str, str]:
        return dict(self._merged().get(section, {}))

    def get_provider(self, name: str) -> dict[str, str]:
        return self.get_section(f"providers.{name}")
