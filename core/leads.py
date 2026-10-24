"""Проверка заявки с сайта.

Сайт проверяет поля ещё в браузере, но доверять браузеру нельзя:
сервер проверяет всё заново этой функцией и сам решает, что сохранить.
"""

from __future__ import annotations

import re
from typing import Any

from core.phones import normalize_phone

# Как клиенту удобнее получить ответ
CHANNELS: dict[str, str] = {"phone": "Звонок", "telegram": "Telegram", "email": "Почта"}

# Когда удобно принять звонок
CALL_TIMES: dict[str, str] = {
    "asap": "Как можно скорее",
    "morning": "Утром, 8–12",
    "day": "Днём, 12–17",
    "weekend": "В выходной",
}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")  # простая проверка «что-то@что-то.ru»
TELEGRAM_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")  # правила Telegram для username

MAX_NAME = 80
MAX_EMAIL = 120
MAX_MESSAGE = 1000


def _text(value: Any, limit: int) -> str:
    """Строка без лишних пробелов и не длиннее limit символов."""
    return " ".join(str(value or "").split())[:limit]


def _truthy(value: Any) -> bool:
    """Галочка из JSON (true) или из обычной формы («on», «1», «да»)."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "да"}


def clean_telegram(raw: Any) -> str:
    """«https://t.me/anna_events», «@anna_events», «anna_events» -> «anna_events»."""
    value = str(raw or "").strip()
    value = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", value, flags=re.IGNORECASE)
    return value.lstrip("@")


def validate_lead(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Проверяет заявку. Возвращает (чистые данные, ошибки по полям).

    Если словарь ошибок пустой — заявку можно сохранять.
    Тексты ошибок показываются клиенту под полями формы.
    """
    errors: dict[str, str] = {}

    name = _text(data.get("name"), MAX_NAME)
    if len(name) < 2:
        errors["name"] = "Укажите имя"

    phone = normalize_phone(str(data.get("phone") or ""))
    if not phone:
        errors["phone"] = "Введите номер полностью"

    email = _text(data.get("email"), MAX_EMAIL)
    if email and not EMAIL_RE.match(email):
        errors["email"] = "Проверьте адрес почты"

    telegram = clean_telegram(data.get("telegram"))
    if telegram and not TELEGRAM_RE.match(telegram):
        errors["telegram"] = "Например: @username"

    channel = data.get("channel") if data.get("channel") in CHANNELS else "phone"
    if channel == "telegram" and not telegram:
        errors.setdefault("telegram", "Укажите Telegram, чтобы мы написали туда")
    if channel == "email" and not email:
        errors.setdefault("email", "Укажите почту, чтобы мы ответили туда")

    call_time = data.get("call_time") if data.get("call_time") in CALL_TIMES else "asap"

    if not _truthy(data.get("consent")):
        errors["consent"] = "Нужно согласие на обработку данных"

    clean = {
        "name": name,
        "phone": phone or "",
        "email": email,
        "telegram": f"@{telegram}" if telegram and "telegram" not in errors else "",
        "channel": channel,
        "call_time": call_time,
        "message": str(data.get("message") or "").strip()[:MAX_MESSAGE],
        # Если клиент снял галочку «Приложить мою смету», расчёт не сохраняем
        "attach_estimate": _truthy(data.get("attach_estimate", True)),
    }
    return clean, errors
