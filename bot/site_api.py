"""Клиент служебного API сайта.

requests работает синхронно: пока ждёт ответа, всё остальное стоит.
Поэтому каждый запрос запускаем в отдельном потоке через asyncio.to_thread —
бот в это время продолжает отвечать другим менеджерам.
"""

from __future__ import annotations

import asyncio
from typing import Any

import requests


class SiteAPIError(RuntimeError):
    """Сайт ответил ошибкой или не ответил вовсе."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SiteAPI:
    def __init__(self, base_url: str, token: str, *, timeout: float = 10, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"X-Internal-Token": token, "Accept": "application/json"})

    def _request_sync(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        except requests.RequestException as error:
            raise SiteAPIError("Сайт не отвечает. Проверьте, что он запущен и SITE_API_URL указан верно.") from error
        try:
            data = response.json()
        except ValueError as error:
            raise SiteAPIError(f"Сайт вернул не JSON (HTTP {response.status_code})", response.status_code) from error
        if response.status_code >= 400 or not data.get("ok"):
            raise SiteAPIError(data.get("error") or f"HTTP {response.status_code}", response.status_code)
        return data

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_sync, method, path, **kwargs)

    async def leads(self, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return (await self._request("GET", "/internal/leads", params=params))["leads"]

    async def lead(self, lead_id: int) -> dict[str, Any]:
        return (await self._request("GET", f"/internal/leads/{lead_id}"))["lead"]

    async def set_status(self, lead_id: int, status: str, actor: str) -> tuple[dict[str, Any], bool]:
        data = await self._request("POST", f"/internal/leads/{lead_id}/status", json={"status": status, "actor": actor})
        return data["lead"], data["changed"]

    async def stats(self, period: str) -> tuple[str, dict[str, Any]]:
        data = await self._request("GET", "/internal/stats", params={"period": period})
        return data["title"], data["stats"]
