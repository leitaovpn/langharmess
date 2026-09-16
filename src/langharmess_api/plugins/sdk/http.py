"""HTTP implementation of the UI-to-server SDK."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any, cast

import httpx
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

from langharmess_api.contracts import UISdkProvider


@ComponentFactory("http-ui-sdk-factory")
@Provides(UISdkProvider)
@Property("_base_url", "plugin.sdk.base_url", "http://127.0.0.1:11534")
@Property("_token", "plugin.sdk.token", "secret")
class HttpUISdk:
    def __init__(self) -> None:
        self._base_url = "http://127.0.0.1:11534"
        self._token = "secret"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=1.0)
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    def get(self, path: str) -> Mapping[str, Any]:
        response = httpx.get(
            f"{self._base_url}/{path.lstrip('/')}", headers=self._headers()
        )
        response.raise_for_status()
        return cast(Mapping[str, Any], response.json())

    def put(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = httpx.put(
            f"{self._base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=dict(payload),
        )
        response.raise_for_status()
        return cast(Mapping[str, Any], response.json())

    async def stream(
        self, payload: Mapping[str, Any]
    ) -> AsyncIterator[Mapping[str, Any]]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/stream",
                headers=self._headers(),
                json=dict(payload),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield json.loads(line)
