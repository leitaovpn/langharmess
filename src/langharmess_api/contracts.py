"""Public service specifications for the API server plugins."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Request

SPEC_API_SERVER = "api.server"
SPEC_AUTH = "api.plugin.auth"
SPEC_RATE_LIMIT = "api.plugin.rate_limit"
SPEC_DB = "api.plugin.db"
SPEC_ROUTE = "api.plugin.route"


@runtime_checkable
class RouteProvider(Protocol):
    def get_router(self) -> APIRouter: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class AuthProvider(Protocol):
    def get_auth_dependency(self) -> Callable[[Request], Any]: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class RateLimitProvider(Protocol):
    def get_rate_limit_dependency(self) -> Callable[[Request], None]: ...

    def get_plugin_info(self) -> dict[str, str]: ...


@runtime_checkable
class DBProvider(Protocol):
    def get_session_dependency(self) -> Callable[[], Any]: ...

    def get_plugin_info(self) -> dict[str, str]: ...
