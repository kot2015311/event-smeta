"""Что происходит, когда приходит заявка или менеджер меняет статус.

Здесь собрана вся «логика бизнеса», а страницы (app/views) только
передают сюда данные и показывают результат. Так одну и ту же заявку
можно принять из формы на сайте, из API и из тестов одинаково.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app import repo
from app.notify import TelegramNotifier
from app.security import RateLimiter
from core import statuses
from core.leads import validate_lead
from core.pricing import apply_overrides, estimate, load_default_prices, normalize_params
from core.schedule import work_status

PRICE_OVERRIDES_KEY = "price_overrides"


def current_prices(db: sqlite3.Connection) -> dict[str, Any]:
    """Прайс из prices.json с правками менеджера из админки."""
    return apply_overrides(load_default_prices(), repo.get_setting(db, PRICE_OVERRIDES_KEY))


@dataclass
class SubmitResult:
    """Ответ на отправку заявки: HTTP-код, текст для клиента, ошибки по полям."""

    status: int
    ok: bool
    message: str = ""
    lead_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict)
    estimate: dict[str, Any] | None = None


def thanks_message(schedule: dict[str, Any], response_minutes: int, now: datetime | None = None) -> str:
    """Что пообещать клиенту после заявки — зависит от того, работаем ли мы сейчас."""
    status = work_status(now, schedule)
    if status["open"]:
        return f"Менеджер перезвонит в течение {response_minutes} минут."
    return f"Сейчас мы не на связи. Перезвоним {status['next']} по московскому времени."


def submit_lead(
    db: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    ip: str,
    limiter: RateLimiter,
    notifier: TelegramNotifier,
    min_seconds: float,
    response_minutes: int,
    source: str = "site",
) -> SubmitResult:
    """Принимает заявку: защита от спама → проверка полей → расчёт сметы → база → Telegram."""
    prices = current_prices(db)
    thanks = thanks_message(prices["schedule"], response_minutes)

    # 1. Ловушка для роботов: поле website спрятано от людей, его заполняют только боты.
    #    Боту отвечаем «успешно», чтобы он не пытался обойти защиту.
    if str(payload.get("website") or "").strip():
        return SubmitResult(200, True, thanks)

    # 2. Человек не заполнит форму быстрее пары секунд, а робот — запросто
    try:
        elapsed = float(payload.get("elapsed_ms")) / 1000
    except (TypeError, ValueError):
        elapsed = None  # поле не прислали (например, форма без JavaScript) — не придираемся
    if elapsed is not None and elapsed < min_seconds:
        return SubmitResult(200, True, thanks)

    # 3. Проверяем поля. Тексты ошибок покажем под полями формы
    clean, errors = validate_lead(payload)
    if errors:
        return SubmitResult(400, False, "Проверьте поля формы", errors=errors)

    # 4. Не больше N заявок с одного адреса за 10 минут
    if not limiter.allow(ip):
        return SubmitResult(429, False, "Слишком много заявок подряд. Попробуйте через несколько минут или позвоните нам.")

    # 5. Смету считаем на сервере заново: цене из браузера не доверяем
    est = None
    if clean["attach_estimate"] and isinstance(payload.get("estimate"), dict):
        est = estimate(normalize_params(payload["estimate"], prices), prices)

    # 6. Сохраняем и сообщаем менеджерам
    utm = {key: str(payload.get(key) or "").strip() for key in ("utm_source", "utm_medium", "utm_campaign")}
    lead_id = repo.create_lead(db, clean, est, utm, source=source)
    notifier.lead_created(repo.get_lead(db, lead_id))
    return SubmitResult(201, True, thanks, lead_id=lead_id, estimate=est)


def change_status(
    db: sqlite3.Connection, lead_id: int, new_status: str, actor: str, notifier: TelegramNotifier
) -> tuple[dict[str, Any] | None, bool]:
    """Меняет статус заявки и обновляет карточку в Telegram."""
    lead, changed = repo.update_status(db, lead_id, new_status, actor)
    if lead and changed:
        notifier.lead_updated(lead)
    return lead, changed


# ---------------------------------------------------------------------------
# Тестовые заявки для демонстрации CRM (команда flask seed-demo)
# ---------------------------------------------------------------------------

_SAMPLE_NAMES = [
    "Анна Соколова",
    "Михаил Петров",
    "Екатерина Морозова",
    "Дмитрий Волков",
    "Ольга Лебедева",
    "Сергей Новиков",
    "Мария Козлова",
    "Алексей Фёдоров",
    "Наталья Егорова",
    "Иван Павлов",
    "Татьяна Орлова",
    "Павел Николаев",
    "Юлия Андреева",
    "Роман Макаров",
    "Ксения Зайцева",
]
_SAMPLE_MESSAGES = [
    "Дата 20 декабря, площадка своя",
    "Нужен ведущий, который говорит по-английски",
    "Бюджет до 500 тысяч, можно уложиться?",
    "Можно выезд в Подмосковье с ночёвкой?",
    "Хотим квест для отдела продаж",
    "Пришлите, пожалуйста, примеры прошлых мероприятий",
    "",
    "",
]
_SAMPLE_SOURCES = ["yandex", "yandex", "vk", "telegram", "", ""]
_SAMPLE_PATHS = [
    ["in_progress"],
    ["in_progress", "quoted"],
    ["in_progress", "quoted", "won"],
    ["in_progress", "lost"],
    ["in_progress", "quoted", "lost"],
]


def seed_sample_leads(db: sqlite3.Connection, count: int = 24, days: int = 14, seed: int = 7) -> int:
    """Создаёт правдоподобные тестовые заявки за последние days дней.

    У всех source = 'sample' и телефоны вида +7 (900) 000-00-XX,
    поэтому их легко отличить и удалить командой flask clear-samples.
    """
    rnd = random.Random(seed)  # одинаковые данные при каждом запуске
    prices = current_prices(db)
    now = datetime.now(UTC)
    created = 0
    for i in range(count):
        age = timedelta(days=rnd.uniform(0, days), hours=rnd.uniform(0, 3))
        created_at = (now - age).isoformat(timespec="seconds")
        preset = rnd.choice(prices["presets"])["state"]
        params = dict(preset) | {
            "format": rnd.choice(prices["formats"])["id"],
            "guests": rnd.choice([20, 35, 50, 60, 80, 120, 150, 200, 300]),
            "level": rnd.choice(["standard", "comfort", "comfort", "premium"]),
        }
        est = estimate(normalize_params(params, prices), prices) if rnd.random() > 0.1 else None
        name = rnd.choice(_SAMPLE_NAMES)
        clean = {
            "name": name,
            "phone": f"+790000000{i % 100:02d}",
            "email": "",
            "telegram": f"@sample_{i:02d}" if rnd.random() > 0.5 else "",
            "channel": rnd.choice(["phone", "phone", "telegram", "email"]),
            "call_time": rnd.choice(["asap", "morning", "day", "weekend"]),
            "message": rnd.choice(_SAMPLE_MESSAGES),
        }
        if clean["channel"] == "telegram" and not clean["telegram"]:
            clean["telegram"] = f"@sample_{i:02d}"
        if clean["channel"] == "email":
            clean["email"] = f"sample{i:02d}@example.ru"
        lead_id = repo.create_lead(
            db, clean, est, {"utm_source": rnd.choice(_SAMPLE_SOURCES)}, source="sample", created_at=created_at
        )
        # Старые заявки чаще уже закрыты, свежие — ещё новые
        if age > timedelta(days=1):
            path = rnd.choice(_SAMPLE_PATHS)
            moment = now - age
            for code in path:
                moment += timedelta(hours=rnd.uniform(0.2, 20))  # менеджер реагирует не мгновенно
                when = min(moment, now).isoformat(timespec="seconds")
                repo.update_status(db, lead_id, code, rnd.choice(["Анна (CRM)", "Иван (Telegram)"]), when=when)
        created += 1
    return created


def clear_sample_leads(db: sqlite3.Connection) -> int:
    """Удаляет тестовые заявки (и их историю — каскадом)."""
    cur = db.execute("DELETE FROM leads WHERE source = 'sample'")
    db.commit()
    return cur.rowcount


def lead_counts_by_status(db: sqlite3.Connection) -> dict[str, int]:
    """Счётчики для вкладок фильтра в CRM."""
    rows = db.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
    counts = {code: 0 for code in statuses.ORDER}
    counts.update({r["status"]: r["n"] for r in rows})
    counts["open"] = sum(counts[c] for c in statuses.OPEN)
    counts["all"] = sum(counts[c] for c in statuses.ORDER)
    return counts
