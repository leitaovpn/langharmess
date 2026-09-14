"""FastAPI server component assembled from plugin services."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Provides,
    Requires,
    RequiresBest,
    UnbindField,
)

from langharmess_api.contracts import (
    SPEC_API_SERVER,
    SPEC_AUTH,
    SPEC_DB,
    SPEC_RATE_LIMIT,
    SPEC_ROUTE,
)
from langharmess_config.contracts import SPEC_CONFIGS
from langharmess_core.common.dependencies import get_db_session
from langharmess_logging.contracts import SPEC_LOG


@ComponentFactory("api-server-factory")
@Provides(SPEC_API_SERVER)
@Requires("_route_providers", SPEC_ROUTE, aggregate=True, optional=True)
@RequiresBest("_auth_provider", SPEC_AUTH, optional=True, immediate_rebind=True)
@RequiresBest("_rate_limit_provider", SPEC_RATE_LIMIT, optional=True, immediate_rebind=True)
@RequiresBest("_db_provider", SPEC_DB, optional=True, immediate_rebind=True)
@RequiresBest("_configs", SPEC_CONFIGS, optional=True, immediate_rebind=True)
@RequiresBest("_log_provider", SPEC_LOG, optional=True, immediate_rebind=True)
class APIServerService:
    """Builds a FastAPI app from the currently injected plugins."""

    def __init__(self) -> None:
        self._route_providers: list[Any] = []
        self._auth_provider: Any = None
        self._rate_limit_provider: Any = None
        self._db_provider: Any = None
        self._configs: Any = None
        self._log_provider: Any = None

    @BindField("_route_providers", if_valid=True)
    def _on_route_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_route_providers", if_valid=True)
    def _on_route_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @BindField("_auth_provider", if_valid=True)
    def _on_auth_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_auth_provider")
    def _on_auth_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @BindField("_rate_limit_provider", if_valid=True)
    def _on_rate_limit_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_rate_limit_provider")
    def _on_rate_limit_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @BindField("_db_provider", if_valid=True)
    def _on_db_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_db_provider")
    def _on_db_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @BindField("_configs", if_valid=True)
    def _on_configs_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_configs")
    def _on_configs_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @BindField("_log_provider", if_valid=True)
    def _on_log_bind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    @UnbindField("_log_provider")
    def _on_log_unbind(self, field: str, service: Any, reference: Any) -> None:
        self._current_app = self.build_app()

    def build_app(self) -> FastAPI:
        app = FastAPI(title="langharmess_api", version="0.1.0")
        app.state.configs = self._configs
        app.state.log = self._log_provider
        if self._log_provider is not None:
            self._log_provider.get_logger().info("API server app built")

        if self._db_provider is not None:
            app.dependency_overrides[get_db_session] = (
                self._db_provider.get_session_dependency()
            )

        dependencies: list[Any] = []
        if self._auth_provider is not None:
            dependencies.append(Depends(self._auth_provider.get_auth_dependency()))
        if self._rate_limit_provider is not None:
            dependencies.append(
                Depends(self._rate_limit_provider.get_rate_limit_dependency())
            )

        for provider in self._route_providers or []:
            app.include_router(provider.get_router(), dependencies=dependencies)

        return app
