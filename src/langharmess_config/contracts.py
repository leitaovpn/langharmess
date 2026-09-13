"""Public contracts for configuration plugins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

SPEC_CONFIG_PROVIDER = "config.plugin"
SPEC_CONFIGS = "configs"


@runtime_checkable
class ConfigProvider(Protocol):
    def get_config(self) -> Mapping[str, Mapping[str, str]]: ...


@runtime_checkable
class Configs(Protocol):
    def get(self, section: str, key: str, fallback: str | None = None) -> str | None: ...

    def get_section(self, section: str) -> Mapping[str, str]: ...

    def get_provider(self, name: str) -> Mapping[str, str]: ...
