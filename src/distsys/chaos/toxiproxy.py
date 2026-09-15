"""Minimal async Toxiproxy HTTP client with explicit named-target validation."""

from __future__ import annotations

from typing import Any

import httpx


class ToxiproxyClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8474",
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            if response.content:
                return response.json()
            return None

    async def create_proxy(self, name: str, listen: str, upstream: str) -> None:
        await self._request(
            "POST",
            "/proxies",
            json={
                "name": name,
                "listen": listen,
                "upstream": upstream,
                "enabled": True,
            },
        )

    async def delete_proxy(self, name: str) -> None:
        try:
            await self._request("DELETE", f"/proxies/{name}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self._request("POST", f"/proxies/{name}", json={"enabled": enabled})

    async def add_latency(
        self,
        name: str,
        toxic_name: str,
        latency_ms: int,
        jitter_ms: int = 0,
    ) -> None:
        await self._request(
            "POST",
            f"/proxies/{name}/toxics",
            json={
                "name": toxic_name,
                "type": "latency",
                "stream": "downstream",
                "toxicity": 1.0,
                "attributes": {"latency": int(latency_ms), "jitter": int(jitter_ms)},
            },
        )

    async def remove_toxic(self, name: str, toxic_name: str) -> None:
        try:
            await self._request("DELETE", f"/proxies/{name}/toxics/{toxic_name}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def proxies(self) -> dict[str, Any]:
        data = await self._request("GET", "/proxies")
        return dict(data or {})
