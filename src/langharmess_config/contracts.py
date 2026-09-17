"""Public contracts for configuration plugins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from langharmess_plugin.validation import service_contract

SPEC_CONFIG_PROVIDER = "config.plugin"
SPEC_CONFIGS = "configs"


@service_contract(SPEC_CONFIG_PROVIDER)
@runtime_checkable
class ConfigProvider(Protocol):
    def get_config(self) -> Mapping[str, Any]: ...


@service_contract(SPEC_CONFIGS)
@runtime_checkable
class Configs(Protocol):
    def get(self, section: str, key: str, fallback: str | None = None) -> str | None: ...

    def get_section(self, section: str) -> Mapping[str, Any]: ...

    def get_provider(self, name: str) -> Mapping[str, Any]: ...

    def get_default_provider(self) -> Mapping[str, Any]: ...

    def list_providers(self) -> list[str]: ...
