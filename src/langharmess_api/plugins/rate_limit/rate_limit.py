"""In-memory sliding window rate limit plugin."""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import HTTPException, Request
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import SPEC_RATE_LIMIT


@ComponentFactory("api-rate-limit-plugin-factory")
@Provides(SPEC_RATE_LIMIT)
@Property("_plugin_name", "plugin.name", "rate-limit")
@Property("_plugin_version", "plugin.version", "1.0.0")
@Property("_limit", "plugin.limit", 2)
@Property("_window_seconds", "plugin.window_seconds", 60.0)
class RateLimitPlugin:
    def __init__(self) -> None:
        self._plugin_name = "rate-limit"
        self._plugin_version = "1.0.0"
        self._limit = 2
        self._window_seconds = 60.0
        self._hits: dict[str, list[float]] = {}

    def get_rate_limit_dependency(self) -> Callable[[Request], None]:
        def dependency(request: Request) -> None:
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            hits = [
                hit
                for hit in self._hits.get(client, [])
                if now - hit < self._window_seconds
            ]
            if len(hits) >= self._limit:
                self._hits[client] = hits
                raise HTTPException(status_code=429, detail="Too Many Requests")
            hits.append(now)
            self._hits[client] = hits

        return dependency

    def get_plugin_info(self) -> dict[str, str]:
        return {"name": self._plugin_name, "version": self._plugin_version}
