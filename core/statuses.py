"""Статусы заявки: путь клиента от звонка до договора."""

from __future__ import annotations

# Порядок важен: так статусы идут в воронке и в админке
STATUSES: dict[str, dict[str, str]] = {
    "new": {"title": "Новая", "emoji": "🆕", "action": "Новая"},
    "in_progress": {"title": "В работе", "emoji": "🟡", "action": "Взял в работу"},
    "quoted": {"title": "Смета отправлена", "emoji": "📄", "action": "Смета отправлена"},
    "won": {"title": "Договор", "emoji": "✅", "action": "Договор"},
    "lost": {"title": "Отказ", "emoji": "✖️", "action": "Отказ"},
}

ORDER: list[str] = list(STATUSES)  # ["new", "in_progress", "quoted", "won", "lost"]
OPEN: frozenset[str] = frozenset({"new", "in_progress", "quoted"})  # с заявкой ещё работают
CLOSED: frozenset[str] = frozenset({"won", "lost"})  # история закончилась


def is_valid(code: str | None) -> bool:
    """Проверяет, что такой статус существует."""
    return code in STATUSES


def title(code: str) -> str:
    """«in_progress» -> «В работе»."""
    return STATUSES.get(code, {}).get("title", code)


def emoji(code: str) -> str:
    """Значок статуса для Telegram."""
    return STATUSES.get(code, {}).get("emoji", "•")
