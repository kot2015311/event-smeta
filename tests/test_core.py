"""Проверка заявки, телефоны, график работы, карточки для Telegram."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core.cards import lead_card, lead_keyboard, parse_callback, stats_text
from core.leads import validate_lead
from core.phones import format_phone, normalize_phone
from core.pricing import estimate, load_default_prices
from core.schedule import local_time, status_text, work_status

SCHEDULE = load_default_prices()["schedule"]


def msk(y, m, d, h, minute=0) -> datetime:
    """Момент времени по Москве."""
    return datetime(y, m, d, h, minute, tzinfo=ZoneInfo("Europe/Moscow"))


# ---------- Телефоны ----------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+7 (999) 123-45-67", "+79991234567"),
        ("8 999 123 45 67", "+79991234567"),
        ("9991234567", "+79991234567"),
        ("+7 999 123", None),
        ("", None),
        ("+1 (555) 123-45-67", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_format_phone():
    assert format_phone("+79991234567") == "+7 (999) 123-45-67"
    assert format_phone("непонятно") == "непонятно"


# ---------- Проверка заявки ----------
def good(**kw):
    data = {"name": "Анна", "phone": "89991234567", "consent": True}
    data.update(kw)
    return data


def test_valid_lead_is_cleaned():
    clean, errors = validate_lead(good(name="  Анна   Петрова ", telegram="https://t.me/anna_events", email="a@b.ru"))
    assert errors == {}
    assert clean["name"] == "Анна Петрова"
    assert clean["phone"] == "+79991234567"
    assert clean["telegram"] == "@anna_events"
    assert clean["channel"] == "phone"
    assert clean["attach_estimate"] is True


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (good(name="А"), "name"),
        (good(phone="12345"), "phone"),
        (good(email="не-почта"), "email"),
        (good(telegram="@ab"), "telegram"),
        (good(channel="telegram"), "telegram"),
        (good(channel="email"), "email"),
        (good(consent=False), "consent"),
        (good(consent="нет"), "consent"),
    ],
)
def test_invalid_fields(data, field):
    _, errors = validate_lead(data)
    assert field in errors


def test_unknown_channel_falls_back_to_phone():
    clean, errors = validate_lead(good(channel="голубиная почта", call_time="ночью"))
    assert errors == {}
    assert clean["channel"] == "phone"
    assert clean["call_time"] == "asap"


def test_form_checkbox_values():
    """Обычная форма присылает «on» вместо true."""
    clean, errors = validate_lead(good(consent="on", attach_estimate=None))
    assert errors == {}
    assert clean["attach_estimate"] is False


# ---------- График работы ----------
@pytest.mark.parametrize(
    ("moment", "is_open", "text"),
    [
        (msk(2026, 10, 26, 9), True, "На связи до 17:00"),  # понедельник утро
        (msk(2026, 10, 26, 7, 30), False, "Перезвоним сегодня в 8:00"),
        (msk(2026, 10, 26, 17), False, "Перезвоним завтра в 8:00"),  # ровно 17:00 — уже закрыто
        (msk(2026, 10, 30, 18), False, "Перезвоним завтра в 10:00"),  # пятница вечер → суббота с 10
        (msk(2026, 10, 24, 12), True, "На связи до 15:00"),  # суббота
        (msk(2026, 10, 25, 16), False, "Перезвоним завтра в 8:00"),  # воскресенье вечер → понедельник с 8
    ],
)
def test_work_status(moment, is_open, text):
    status = work_status(moment, SCHEDULE)
    assert status["open"] is is_open
    assert status_text(status) == text


def test_local_time():
    assert local_time("2026-10-24T09:30:00+00:00", "Europe/Moscow") == "24.10 12:30"
    assert local_time("2026-10-24T09:30:00", "Europe/Moscow") == "24.10 12:30"  # без пояса — считаем UTC


# ---------- Карточки Telegram ----------
def sample_lead(**kw):
    prices = load_default_prices()
    lead = {
        "id": 7,
        "status": "new",
        "name": "<b>Хакер</b> & Ко",
        "phone": "+79991234567",
        "email": "",
        "telegram": "@anna_events",
        "channel": "telegram",
        "call_time": "day",
        "message": "Нужен <script>",
        "utm_source": "yandex",
        "created_at": "2026-10-26T06:00:00+00:00",  # понедельник, 9:00 МСК
        "updated_at": "2026-10-26T06:00:00+00:00",
        "estimate": estimate({"format": "corporate", "guests": 80, "hours": 4, "level": "standard", "addons": ["host"]}, prices),
    }
    lead.update(kw)
    return lead


def test_card_escapes_user_input():
    card = lead_card(sample_lead(), SCHEDULE)
    assert "&lt;b&gt;Хакер&lt;/b&gt; &amp; Ко" in card
    assert "<script>" not in card
    assert "Заявка №7" in card
    assert "Корпоратив" in card
    assert "+7 (999) 123-45-67" in card
    assert "Источник: yandex" in card
    assert "рабочее время" in card


def test_card_without_estimate_and_after_hours():
    card = lead_card(sample_lead(estimate=None, created_at="2026-10-26T20:00:00+00:00"), SCHEDULE)
    assert "Смету не приложил" in card
    assert "завтра в 8:00" in card


def test_keyboard_for_open_and_closed_leads():
    open_rows = lead_keyboard(7, "in_progress", "https://smeta.example.ru/admin/leads/7")
    texts = [b["text"] for row in open_rows for b in row]
    assert "✓ В работе" in texts
    assert any(b.get("url") for row in open_rows for b in row)
    closed = lead_keyboard(7, "won", "http://localhost/admin/leads/7")  # не https — без кнопки-ссылки
    assert closed == [[{"text": "↩️ Вернуть в работу", "callback_data": "st:7:in_progress"}]]


@pytest.mark.parametrize(
    ("data", "expected"),
    [("st:12:won", (12, "won")), ("st:12:hacked", None), ("st:x:won", None), ("other", None), (None, None)],
)
def test_parse_callback(data, expected):
    assert parse_callback(data) == expected


def test_stats_text():
    empty = {"total": 0, "by_status": {}, "waiting": 0}
    assert "Заявок пока нет" in stats_text(empty, "Сегодня")
    stats = {
        "total": 3,
        "by_status": {"new": 1, "won": 2},
        "avg_estimate": 450000,
        "sum_estimate": 1350000,
        "top_formats": [("Корпоратив", 2)],
        "waiting": 1,
    }
    text = stats_text(stats, "За 7 дней")
    assert "Заявок: <b>3</b>" in text
    assert "Договор: 2" in text
    assert "Чаще всего: Корпоратив (2)" in text
