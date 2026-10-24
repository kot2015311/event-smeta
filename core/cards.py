"""Тексты для Telegram: карточка заявки, кнопки статусов, сводки.

Сайт отправляет карточку, когда приходит заявка, а бот показывает
те же карточки по командам. Поэтому формат живёт в одном месте.
Telegram понимает простой HTML: <b>, <i>, <a>. Всё, что ввёл клиент,
обязательно экранируем, иначе «<» в имени сломает сообщение.
"""

from __future__ import annotations

from html import escape
from typing import Any

from core import statuses
from core.fmt import guests_nom, hours_label, money, num, short_range
from core.leads import CALL_TIMES, CHANNELS
from core.phones import format_phone
from core.schedule import local_time, parse_iso, work_status

CALLBACK_PREFIX = "st"  # данные кнопки: «st:12:won» = заявка 12 -> статус «Договор»


def _e(value: Any) -> str:
    """Экранирует текст для HTML-разметки Telegram."""
    return escape(str(value or ""), quote=False)


def lead_title(lead: dict[str, Any]) -> str:
    """«🆕 Заявка №12 · Новая»."""
    status = lead.get("status", "new")
    return f"{statuses.emoji(status)} <b>Заявка №{lead['id']}</b> · {_e(statuses.title(status))}"


def estimate_block(est: dict[str, Any] | None) -> list[str]:
    """Строки про смету. Если клиент её не приложил — честно пишем об этом."""
    if not est:
        return ["💰 Смету не приложил, нужен расчёт по звонку"]
    addons = [line["title"].lower() for line in est["lines"][1:]]
    what = (
        f"<b>{_e(est['format']['title'])}</b>, «{_e(est['level']['title'])}», "
        f"{guests_nom(est['guests'])}, {hours_label(est['hours'])}"
    )
    rows = [
        what,
        f"💰 <b>{num(est['low'])} – {money(est['high'])}</b>",
        f"≈ {money(est['total'])} · {money(est['per_guest'])} на гостя",
    ]
    rows.append("Услуги: " + (_e(", ".join(addons)) if addons else "только организация"))
    return rows


def lead_card(lead: dict[str, Any], schedule: dict[str, Any]) -> str:
    """Полная карточка заявки для менеджера."""
    rows = [lead_title(lead), ""]
    rows += estimate_block(lead.get("estimate"))
    rows.append("")

    rows.append(f"👤 <b>{_e(lead['name'])}</b>")
    rows.append(f"📞 {_e(format_phone(lead['phone']))}")
    if lead.get("telegram"):
        rows.append(f"✈️ {_e(lead['telegram'])}")
    if lead.get("email"):
        rows.append(f"📧 {_e(lead['email'])}")
    channel = CHANNELS.get(lead.get("channel", "phone"), "Звонок")
    call_time = CALL_TIMES.get(lead.get("call_time", "asap"), "")
    rows.append(f"🕐 Связаться: {_e(channel.lower())}, {_e(call_time.lower())}")
    if lead.get("message"):
        rows.append(f"📝 «{_e(lead['message'])}»")
    if lead.get("utm_source"):
        rows.append(f"📈 Источник: {_e(lead['utm_source'])}")

    # Подсказка менеджеру, когда перезванивать: считаем по времени заявки
    rows.append("")
    when = work_status(parse_iso(lead["created_at"]), schedule)
    tz_label = schedule.get("tz_label", "")
    if when["open"]:
        rows.append(f"⏰ Пришла в рабочее время ({local_time(lead['created_at'], schedule['tz'])}). Позвоните как можно скорее.")
    else:
        rows.append(f"🌙 Пришла в нерабочее время. Клиент ждёт звонка {when['next']} ({tz_label}).")

    # Кто и когда последний раз менял статус
    if lead.get("status") != "new" and lead.get("status_actor"):
        changed = local_time(lead.get("status_at") or lead["updated_at"], schedule["tz"])
        rows.append(f"Статус «{_e(statuses.title(lead['status']))}»: {_e(lead['status_actor'])}, {changed}")
    return "\n".join(rows)


def lead_keyboard(lead_id: int, status: str, crm_url: str | None = None) -> list[list[dict[str, str]]]:
    """Кнопки под карточкой в формате Telegram Bot API (inline_keyboard).

    Пока заявка в работе — четыре кнопки статусов (текущий отмечен галочкой).
    Когда закрыта (договор или отказ) — одна кнопка «Вернуть в работу».
    """

    def button(code: str, text: str | None = None) -> dict[str, str]:
        label = text or f"{statuses.emoji(code)} {statuses.STATUSES[code]['action']}"
        if code == status:
            label = "✓ " + statuses.title(code)
        return {"text": label, "callback_data": f"{CALLBACK_PREFIX}:{lead_id}:{code}"}

    if status in statuses.CLOSED:
        rows = [[button("in_progress", "↩️ Вернуть в работу")]]
    else:
        rows = [
            [button("in_progress"), button("quoted")],
            [button("won"), button("lost")],
        ]
    # Ссылку Telegram примет только на настоящий сайт (https), не на localhost
    if crm_url and crm_url.startswith("https://"):
        rows.append([{"text": "Открыть в CRM", "url": crm_url}])
    return rows


def parse_callback(data: str | None) -> tuple[int, str] | None:
    """«st:12:won» -> (12, "won"). Всё непонятное -> None."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return None
    lead_id, code = parts[1], parts[2]
    if not lead_id.isdigit() or not statuses.is_valid(code):
        return None
    return int(lead_id), code


def lead_line(lead: dict[str, Any], schedule: dict[str, Any]) -> str:
    """Короткая строка для списков в боте (/new)."""
    est = lead.get("estimate")
    what = (
        f"{_e(est['format']['title'])}, {guests_nom(est['guests'])} · {short_range(est['low'], est['high'])}"
        if est
        else "без сметы"
    )
    return (
        f"{statuses.emoji(lead['status'])} <b>№{lead['id']}</b> · {what}\n"
        f"{_e(lead['name'])}, {_e(format_phone(lead['phone']))} · {local_time(lead['created_at'], schedule['tz'])}"
    )


def stats_text(stats: dict[str, Any], title: str) -> str:
    """Сводка для команд /today и /stats."""
    if not stats["total"]:
        return f"<b>{_e(title)}</b>\n\nЗаявок пока нет."
    rows = [f"<b>{_e(title)}</b>", ""]
    rows.append(f"Заявок: <b>{stats['total']}</b>")
    for code in statuses.ORDER:
        count = stats["by_status"].get(code, 0)
        if count:
            rows.append(f"{statuses.emoji(code)} {statuses.title(code)}: {count}")
    if stats.get("avg_estimate"):
        rows.append("")
        rows.append(f"Средняя смета: {money(stats['avg_estimate'])}")
        rows.append(f"Сумма смет: {money(stats['sum_estimate'])}")
    if stats.get("top_formats"):
        best, count = stats["top_formats"][0]
        rows.append(f"Чаще всего: {_e(best)} ({count})")
    rows.append("")
    rows.append(f"Ждут звонка прямо сейчас: <b>{stats['waiting']}</b>")
    return "\n".join(rows)
