"""Настройки бота из .env (тот же файл, что и у сайта)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _ids(raw: str) -> frozenset[int]:
    """«123, 456» -> {123, 456}. Лишние пробелы и пустые куски пропускаем."""
    return frozenset(int(part) for part in raw.replace(" ", "").split(",") if part.lstrip("-").isdigit())


@dataclass(frozen=True)
class BotConfig:
    token: str  # токен от @BotFather
    chat_id: int | None  # чат менеджеров, куда сайт присылает заявки
    site_url: str  # адрес сайта для служебного API, например http://127.0.0.1:5000
    api_token: str  # общий секрет с сайтом (INTERNAL_API_TOKEN)
    manager_ids: frozenset[int] = field(default_factory=frozenset)  # кому ещё можно писать боту в личку

    @classmethod
    def from_env(cls) -> BotConfig:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        api_token = os.getenv("INTERNAL_API_TOKEN", "").strip()
        missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("INTERNAL_API_TOKEN", api_token)) if not value]
        if missing:
            raise SystemExit(f"Заполните в .env: {', '.join(missing)}")
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        return cls(
            token=token,
            chat_id=int(chat) if chat.lstrip("-").isdigit() else None,
            site_url=os.getenv("SITE_API_URL", "http://127.0.0.1:5000").strip().rstrip("/"),
            api_token=api_token,
            manager_ids=_ids(os.getenv("MANAGER_IDS", "")),
        )
