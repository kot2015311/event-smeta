"""График работы агентства: открыто ли сейчас и когда перезвоним.

Повторяет функцию workStatus() из app/static/js/engine.js,
чтобы сайт и уведомления в Telegram говорили одно и то же.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _hours_for(js_weekday: int, schedule: dict) -> list[int]:
    """Часы работы для дня недели. 0 — воскресенье, 6 — суббота (как в JavaScript)."""
    return schedule["weekend"] if js_weekday in (0, 6) else schedule["weekday"]


def work_status(now: datetime | None, schedule: dict) -> dict:
    """Возвращает {"open": bool, "closes": 17, "next": "завтра в 8:00", "wd": 3}.

    now — любое время с часовым поясом (по умолчанию «сейчас»);
    schedule — раздел "schedule" из prices.json.
    """
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(schedule["tz"]))  # переводим во время агентства (Москва)
    wd = (local.weekday() + 1) % 7  # в Python понедельник = 0, в JS воскресенье = 0
    start, end = _hours_for(wd, schedule)
    minutes = local.hour * 60 + local.minute
    if start * 60 <= minutes < end * 60:
        return {"open": True, "closes": end, "next": "", "wd": wd}
    if minutes < start * 60:
        return {"open": False, "closes": None, "next": f"сегодня в {start}:00", "wd": wd}
    tomorrow_start = _hours_for((wd + 1) % 7, schedule)[0]
    return {"open": False, "closes": None, "next": f"завтра в {tomorrow_start}:00", "wd": wd}


def parse_iso(value: str) -> datetime:
    """Читает время из базы («2026-10-24T12:30:00+00:00»). Время без пояса считаем UTC."""
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def local_time(value: str | datetime, tz: str, fmt: str = "%d.%m %H:%M") -> str:
    """Время для людей по часам агентства: «24.10 15:42»."""
    dt = parse_iso(value) if isinstance(value, str) else value
    return dt.astimezone(ZoneInfo(tz)).strftime(fmt)


def status_text(status: dict) -> str:
    """Короткая строка для шапки сайта: «На связи до 17:00» / «Перезвоним завтра в 8:00»."""
    if status["open"]:
        return f"На связи до {status['closes']}:00"
    return f"Перезвоним {status['next']}"
