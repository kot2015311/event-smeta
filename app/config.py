"""Настройки сайта. Всё берётся из переменных окружения (файла .env).

Секреты (пароли, токены) никогда не пишем в код — только в .env,
который не попадает в git (см. .gitignore и .env.example).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # корень проекта
load_dotenv(BASE_DIR / ".env")  # читаем .env, если он есть


def _env(name: str, default: str = "") -> str:
    """Строка из окружения без пробелов по краям.

    Пустая строка в .env (например, «SECRET_KEY=») считается незаполненной,
    и тогда берётся значение по умолчанию.
    """
    value = (os.getenv(name) or "").strip()
    return value or default


def _flag(name: str, default: bool = False) -> bool:
    """«1», «true», «yes» -> True."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Настройки по умолчанию. В тестах часть из них подменяется."""

    # Секрет для подписи cookie сессии. В продакшене обязательно своя длинная строка!
    SECRET_KEY = _env("SECRET_KEY", "dev-only-secret-change-me")

    # Файл базы SQLite. По умолчанию — папка instance/ рядом с проектом
    DATABASE_PATH = _env("DATABASE_PATH", str(BASE_DIR / "instance" / "smeta.db"))

    # Агентство: показывается на сайте и в письмах
    AGENCY_NAME = _env("AGENCY_NAME", "Смета за минуту")
    AGENCY_PHONE = _env("AGENCY_PHONE", "+7 (000) 000-00-00")
    AGENCY_EMAIL = _env("AGENCY_EMAIL", "hello@example.ru")
    AGENCY_TELEGRAM = _env("AGENCY_TELEGRAM", "@your_agency")
    RESPONSE_MINUTES = int(_env("RESPONSE_MINUTES", "15") or 15)  # за сколько минут перезваниваем днём

    # Публичный адрес сайта (для ссылок в Telegram, sitemap и соцсетей)
    SITE_URL = _env("SITE_URL", "").rstrip("/")

    # Внешний вид: classic («Классика») или bright («Яркая»)
    SITE_SKIN = _env("SITE_SKIN", "classic")
    SKIN_SWITCHER = _flag("SKIN_SWITCHER", True)  # показывать переключатель стилей

    # Вход в мини-CRM
    ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "")

    # Telegram: токен бота от @BotFather и чат менеджеров
    TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID", "")
    TELEGRAM_API_URL = _env("TELEGRAM_API_URL", "https://api.telegram.org")
    TELEGRAM_ASYNC = True  # отправлять в фоне, чтобы клиент не ждал ответа Telegram

    # Общий секрет между сайтом и ботом для служебного API
    INTERNAL_API_TOKEN = _env("INTERNAL_API_TOKEN", "")

    # Защита формы от спама
    LEAD_RATE_LIMIT = int(_env("LEAD_RATE_LIMIT", "5") or 5)  # заявок с одного адреса…
    LEAD_RATE_WINDOW = int(_env("LEAD_RATE_WINDOW", "600") or 600)  # …за столько секунд
    LEAD_MIN_SECONDS = float(_env("LEAD_MIN_SECONDS", "3") or 3)  # быстрее человек форму не заполнит

    # Сайт стоит за nginx или другим прокси — тогда IP клиента берём из заголовков
    TRUST_PROXY = _flag("TRUST_PROXY", False)

    # Cookie сессии: недоступна из JS, не уходит на чужие сайты
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = SITE_URL.startswith("https://")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 часов

    # Демо-сборка (статичная страница без сервера)
    DEMO_REPO_URL = _env("DEMO_REPO_URL", "https://github.com/kot2015311/event-smeta")
