"""Работа с таблицами: все SQL-запросы проекта собраны здесь.

Функции принимают подключение db первым аргументом. Так их легко вызывать
и из запроса к сайту, и из фоновой задачи, и из тестов.
Значения всегда передаём через «?», а не вклеиваем в строку —
это защищает от SQL-инъекций.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from core import statuses


def now_iso() -> str:
    """Текущее время в UTC: «2026-10-24T12:30:00+00:00»."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------


def _lead_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Строка таблицы -> словарь. Смету распаковываем из JSON."""
    if row is None:
        return None
    lead = dict(row)
    lead["estimate"] = json.loads(lead["estimate_json"]) if lead.get("estimate_json") else None
    return lead


def create_lead(
    db: sqlite3.Connection,
    clean: dict[str, Any],
    estimate: dict[str, Any] | None,
    utm: dict[str, str] | None = None,
    *,
    source: str = "site",
    created_at: str | None = None,
) -> int:
    """Сохраняет новую заявку и первую запись в её истории. Возвращает номер заявки."""
    created = created_at or now_iso()
    utm = utm or {}
    est = estimate or {}
    cur = db.execute(
        """
        INSERT INTO leads (
            created_at, updated_at, status, name, phone, email, telegram, channel, call_time, message,
            has_estimate, format_id, level_id, guests, hours, estimate_total, estimate_low, estimate_high,
            estimate_json, utm_source, utm_medium, utm_campaign, source
        ) VALUES (?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created,
            created,
            clean["name"],
            clean["phone"],
            clean.get("email", ""),
            clean.get("telegram", ""),
            clean.get("channel", "phone"),
            clean.get("call_time", "asap"),
            clean.get("message", ""),
            1 if estimate else 0,
            est.get("format", {}).get("id"),
            est.get("level", {}).get("id"),
            est.get("guests"),
            est.get("hours"),
            est.get("total"),
            est.get("low"),
            est.get("high"),
            json.dumps(estimate, ensure_ascii=False) if estimate else None,
            utm.get("utm_source", "")[:100],
            utm.get("utm_medium", "")[:100],
            utm.get("utm_campaign", "")[:100],
            source,
        ),
    )
    lead_id = int(cur.lastrowid)
    db.execute(
        "INSERT INTO lead_events (lead_id, created_at, kind, actor, new_status, text) VALUES (?, ?, 'created', ?, 'new', ?)",
        (lead_id, created, "Сайт", "Заявка с сайта" if source == "site" else "Тестовая заявка"),
    )
    db.commit()
    return lead_id


def get_lead(db: sqlite3.Connection, lead_id: int) -> dict[str, Any] | None:
    """Одна заявка + кто и когда последним менял статус."""
    lead = _lead_from_row(db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())
    if lead is None:
        return None
    last = db.execute(
        "SELECT actor, created_at FROM lead_events WHERE lead_id = ? AND kind = 'status' ORDER BY id DESC LIMIT 1",
        (lead_id,),
    ).fetchone()
    lead["status_actor"] = last["actor"] if last else ""
    lead["status_at"] = last["created_at"] if last else ""
    return lead


def _filters(status: str | None, format_id: str | None, q: str | None) -> tuple[str, list[Any]]:
    """Собирает условие WHERE для списка заявок из фильтров админки."""
    where, args = [], []
    if status:
        if status == "open":  # все незакрытые
            where.append("status IN ('new', 'in_progress', 'quoted')")
        else:
            where.append("status = ?")
            args.append(status)
    if format_id:
        where.append("format_id = ?")
        args.append(format_id)
    if q:
        # Ищем по имени, телефону, почте и Telegram. Цифры из запроса ищем в телефоне отдельно
        like = f"%{q.strip()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        part = "(name LIKE ? OR email LIKE ? OR telegram LIKE ? OR message LIKE ?"
        args += [like, like, like, like]
        if digits:
            part += " OR phone LIKE ?"
            args.append(f"%{digits}%")
        if q.strip().lstrip("№#").isdigit():  # «№12» — ищем по номеру заявки
            part += " OR id = ?"
            args.append(int(q.strip().lstrip("№#")))
        where.append(part + ")")
    return (" WHERE " + " AND ".join(where)) if where else "", args


def list_leads(
    db: sqlite3.Connection,
    *,
    status: str | None = None,
    format_id: str | None = None,
    q: str | None = None,
    limit: int | None = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Список заявок (новые сверху) и общее количество с учётом фильтров."""
    where, args = _filters(status, format_id, q)
    total = db.execute(f"SELECT COUNT(*) FROM leads{where}", args).fetchone()[0]
    sql = f"SELECT * FROM leads{where} ORDER BY id DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        args = [*args, limit, offset]
    rows = [_lead_from_row(r) for r in db.execute(sql, args).fetchall()]
    return rows, int(total)


def update_status(
    db: sqlite3.Connection, lead_id: int, new_status: str, actor: str, *, when: str | None = None
) -> tuple[dict | None, bool]:
    """Меняет статус и пишет это в историю. Возвращает (заявка, изменилось ли что-то)."""
    if not statuses.is_valid(new_status):
        raise ValueError(f"Неизвестный статус: {new_status}")
    lead = get_lead(db, lead_id)
    if lead is None:
        return None, False
    if lead["status"] == new_status:  # нажали ту же кнопку ещё раз
        return lead, False
    when = when or now_iso()
    db.execute("UPDATE leads SET status = ?, updated_at = ? WHERE id = ?", (new_status, when, lead_id))
    db.execute(
        "INSERT INTO lead_events (lead_id, created_at, kind, actor, old_status, new_status) VALUES (?, ?, 'status', ?, ?, ?)",
        (lead_id, when, actor[:80], lead["status"], new_status),
    )
    db.commit()
    return get_lead(db, lead_id), True


def add_note(db: sqlite3.Connection, lead_id: int, text: str, actor: str) -> None:
    """Заметка менеджера: «перезвонить в среду», «просят скидку»."""
    when = now_iso()
    db.execute(
        "INSERT INTO lead_events (lead_id, created_at, kind, actor, text) VALUES (?, ?, 'note', ?, ?)",
        (lead_id, when, actor[:80], text.strip()[:2000]),
    )
    db.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (when, lead_id))
    db.commit()


def lead_events(db: sqlite3.Connection, lead_id: int) -> list[dict[str, Any]]:
    """История заявки, новые события сверху."""
    rows = db.execute("SELECT * FROM lead_events WHERE lead_id = ? ORDER BY id DESC", (lead_id,)).fetchall()
    return [dict(r) for r in rows]


def set_tg_message_id(db: sqlite3.Connection, lead_id: int, message_id: int) -> None:
    """Запоминаем сообщение в Telegram, чтобы потом обновлять в нём статус."""
    db.execute("UPDATE leads SET tg_message_id = ? WHERE id = ?", (message_id, lead_id))
    db.commit()


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------


def stats(db: sqlite3.Connection, prices: dict[str, Any], since: datetime | None = None) -> dict[str, Any]:
    """Сводка по заявкам с даты since (или за всё время)."""
    args: list[Any] = []
    where = ""
    if since is not None:
        where = " WHERE created_at >= ?"
        args.append(since.astimezone(UTC).isoformat(timespec="seconds"))
    rows = [_lead_from_row(r) for r in db.execute(f"SELECT * FROM leads{where}", args).fetchall()]

    by_status = Counter(r["status"] for r in rows)
    with_estimate = [r for r in rows if r["has_estimate"]]
    totals = [r["estimate_total"] for r in with_estimate]

    format_titles = {f["id"]: f["title"] for f in prices["formats"]}
    addon_titles = {a["id"]: a["title"] for a in prices["addons"]}
    formats = Counter(format_titles.get(r["format_id"], r["format_id"]) for r in with_estimate)
    addons = Counter(addon_titles.get(a, a) for r in with_estimate for a in (r["estimate"] or {}).get("addons", []))
    sources = Counter(r["utm_source"] or "без метки" for r in rows)

    waiting = db.execute("SELECT COUNT(*) FROM leads WHERE status = 'new'").fetchone()[0]
    return {
        "total": len(rows),
        "by_status": {code: by_status.get(code, 0) for code in statuses.ORDER},
        "won": by_status.get("won", 0),
        "conversion": (by_status.get("won", 0) / len(rows)) if rows else 0.0,
        "avg_estimate": int(round(sum(totals) / len(totals), -3)) if totals else 0,  # до тысяч: точнее смету не назвать
        "sum_estimate": sum(totals),
        "won_sum": sum(r["estimate_total"] or 0 for r in with_estimate if r["status"] == "won"),
        "top_formats": formats.most_common(5),
        "top_addons": addons.most_common(6),
        "sources": sources.most_common(5),
        "waiting": int(waiting),
    }


def leads_per_day(db: sqlite3.Connection, days: int, tz: str, today: datetime | None = None) -> list[tuple[str, int]]:
    """Сколько заявок пришло в каждый из последних days дней (по московскому времени)."""
    zone = ZoneInfo(tz)
    today_local = (today or datetime.now(UTC)).astimezone(zone).date()
    first_day = today_local - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=zone)
    rows = db.execute(
        "SELECT created_at FROM leads WHERE created_at >= ?",
        (since.astimezone(UTC).isoformat(timespec="seconds"),),
    ).fetchall()
    counts = Counter(datetime.fromisoformat(r["created_at"]).astimezone(zone).date() for r in rows)
    return [((first_day + timedelta(days=i)).isoformat(), counts.get(first_day + timedelta(days=i), 0)) for i in range(days)]


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------


def get_setting(db: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """Читает настройку (хранится как JSON)."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(db: sqlite3.Connection, key: str, value: Any) -> None:
    """Сохраняет настройку. Если такая уже есть — перезаписывает."""
    db.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, ensure_ascii=False), now_iso()),
    )
    db.commit()


def delete_setting(db: sqlite3.Connection, key: str) -> None:
    """Удаляет настройку (например, «сбросить цены»)."""
    db.execute("DELETE FROM settings WHERE key = ?", (key,))
    db.commit()
