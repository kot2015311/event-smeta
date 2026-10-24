"""Логика бота без aiogram: кого пускать, что ответить. Легко проверить тестами."""

from __future__ import annotations

import re
from typing import Any

from core import statuses
from core.cards import lead_card, lead_line, stats_text

HELP = (
    "<b>Бот заявок агентства</b>\n\n"
    "Новые заявки приходят сюда сами, с кнопками статусов под карточкой.\n\n"
    "/new — заявки, которые ждут звонка\n"
    "/open — все незакрытые заявки\n"
    "/today — сводка за сегодня\n"
    "/week — сводка за 7 дней\n"
    "/lead 12 — карточка заявки №12"
)

LEAD_LINK_RE = re.compile(r"^/lead_(\d+)(?:@\w+)?$")  # «/lead_12» в списке кликабельна


def is_allowed(chat_id: int, user_id: int | None, managers_chat: int | None, manager_ids: frozenset[int]) -> bool:
    """Пускаем: всех в чате менеджеров и тех, чьи id перечислены в MANAGER_IDS.

    Если ни чат, ни список не заданы — бот открыт для всех (удобно при первой настройке,
    но в работе обязательно укажите TELEGRAM_CHAT_ID).
    """
    if managers_chat is None and not manager_ids:
        return True
    return chat_id == managers_chat or (user_id is not None and user_id in manager_ids)


def actor_name(first_name: str | None, last_name: str | None, username: str | None) -> str:
    """Подпись для истории заявки: «Иван Петров (Telegram)»."""
    name = " ".join(part for part in (first_name, last_name) if part) or (f"@{username}" if username else "Менеджер")
    return f"{name} (Telegram)"


def parse_lead_id(text: str | None) -> int | None:
    """Номер заявки из «/lead 12», «/lead №12» или «/lead_12»."""
    if not text:
        return None
    link = LEAD_LINK_RE.match(text.strip())
    if link:
        return int(link.group(1))
    parts = text.strip().split(maxsplit=1)  # ["/lead", "№12"]
    if len(parts) < 2:
        return None
    digits = re.sub(r"\D", "", parts[1])
    return int(digits) if digits else None


def leads_list_text(leads: list[dict[str, Any]], total: int | None, title: str, schedule: dict[str, Any]) -> str:
    """Список заявок для /new и /open. Под каждой — ссылка-команда на карточку."""
    if not leads:
        return f"<b>{title}</b>\n\nПусто. Хорошая работа!"
    rows = [f"<b>{title}</b>" + (f" ({total})" if total and total > len(leads) else ""), ""]
    for lead in leads:
        rows.append(lead_line(lead, schedule))
        rows.append(f"Карточка: /lead_{lead['id']}")
        rows.append("")
    if total and total > len(leads):
        rows.append(f"Показаны последние {len(leads)}. Остальные — в CRM.")
    return "\n".join(rows).strip()


def status_toast(lead: dict[str, Any], changed: bool) -> str:
    """Короткое всплывающее уведомление после нажатия кнопки."""
    title = statuses.title(lead["status"])
    return f"№{lead['id']}: {title}" if changed else f"У заявки №{lead['id']} уже статус «{title}»"


__all__ = ["HELP", "actor_name", "is_allowed", "lead_card", "leads_list_text", "parse_lead_id", "stats_text", "status_toast"]
