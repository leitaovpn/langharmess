"""Aggregate all registered configuration providers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from pelix.ipopo.decorators import ComponentFactory, Provides, Requires

from langharmess_config.contracts import SPEC_CONFIG_PROVIDER, SPEC_CONFIGS

LOGGER = logging.getLogger("langharmess.config")

SUPPORTED_PROTOCOLS = {"anthropic", "chat", "responses"}


@ComponentFactory("configs-plugin-factory")
@Provides(SPEC_CONFIGS)
@Requires("_providers", SPEC_CONFIG_PROVIDER, aggregate=True, optional=True)
class ConfigsPlugin:
    def __init__(self) -> None:
        self._providers: list[Any] = []

    def _merged(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        provider_names: set[str] = set()
        for provider in self._providers or []:
            config = provider.get_config()
            configured_providers = config.get("providers", {})
            if isinstance(configured_providers, Mapping):
                duplicates = provider_names.intersection(configured_providers)
                if duplicates:
                    name = sorted(duplicates)[0]
                    raise ValueError(f"Duplicate provider name: {name}")
                provider_names.update(str(name) for name in configured_providers)
            self._merge_into(merged, config)
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

    def get(self, section: str, key: str, fallback: str | None = None) -> str | None:
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
        provider = self.get_section(f"providers.{name}")
        if not provider:
            return {}
        protocol = provider.get("protocol", "chat")
        if protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"Unsupported protocol for provider {name}: {protocol}")
        model = provider.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"Provider {name} requires a non-empty model")
        for field in ("api_key", "base_url"):
            value = provider.get(field, "")
            if not isinstance(value, str):
                raise ValueError(f"Provider {name} field {field} must be a string")
        return {**provider, "protocol": protocol}

    def list_providers(self) -> list[str]:
        providers = self._merged().get("providers", {})
        if not isinstance(providers, Mapping):
            return []
        names = sorted(
            str(name) for name, value in providers.items() if isinstance(value, Mapping)
        )
        valid: list[str] = []
        for name in names:
            try:
                self.get_provider(name)
            except ValueError as exc:
                LOGGER.warning("Skipping invalid provider %s: %s", name, exc)
                continue
            valid.append(name)
        return valid
