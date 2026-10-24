"""Служебный API для бота и сам бот: логика, клиент API, обработчики aiogram."""

from __future__ import annotations

import asyncio
import threading

import pytest
from werkzeug.serving import make_server

from app import repo
from bot.logic import actor_name, is_allowed, leads_list_text, parse_lead_id, status_toast
from bot.site_api import SiteAPI, SiteAPIError
from core.pricing import load_default_prices
from tests.conftest import INTERNAL_TOKEN, lead_payload

SCHEDULE = load_default_prices()["schedule"]
HEADERS = {"X-Internal-Token": INTERNAL_TOKEN}


# ---------- Служебный API ----------
def test_internal_requires_token(app, client):
    assert client.get("/internal/leads").status_code == 401
    assert client.get("/internal/leads", headers={"X-Internal-Token": "wrong"}).status_code == 401
    app.config["INTERNAL_API_TOKEN"] = ""
    assert client.get("/internal/leads", headers=HEADERS).status_code == 503


def test_internal_status_flow(client, db, telegram):
    lead_id = client.post("/api/leads", json=lead_payload()).get_json()["id"]
    data = client.get("/internal/leads?status=new", headers=HEADERS).get_json()
    assert [lead["id"] for lead in data["leads"]] == [lead_id]
    assert "estimate_json" not in data["leads"][0]

    response = client.post(
        f"/internal/leads/{lead_id}/status", json={"status": "in_progress", "actor": "Иван (Telegram)"}, headers=HEADERS
    )
    body = response.get_json()
    assert body["changed"] is True
    assert body["lead"]["status"] == "in_progress"
    assert telegram.methods() == ["sendMessage", "editMessageText"]  # карточка в чате обновилась

    again = client.post(f"/internal/leads/{lead_id}/status", json={"status": "in_progress"}, headers=HEADERS).get_json()
    assert again["changed"] is False
    assert repo.get_lead(db, lead_id)["status_actor"] == "Иван (Telegram)"


def test_internal_errors(client):
    assert client.get("/internal/leads/999", headers=HEADERS).status_code == 404
    assert client.get("/internal/leads?status=bad", headers=HEADERS).status_code == 400
    assert client.post("/internal/leads/1/status", json={"status": "bad"}, headers=HEADERS).status_code == 400
    assert client.get("/internal/stats?period=year", headers=HEADERS).status_code == 400


def test_internal_stats(client):
    client.post("/api/leads", json=lead_payload())
    data = client.get("/internal/stats?period=today", headers=HEADERS).get_json()
    assert data["title"] == "Сегодня"
    assert data["stats"]["total"] == 1
    assert data["stats"]["waiting"] == 1


# ---------- Логика бота ----------
def test_is_allowed():
    managers = frozenset({42})
    assert is_allowed(-1001, 7, -1001, frozenset())  # чат менеджеров
    assert is_allowed(42, 42, -1001, managers)  # менеджер в личке
    assert not is_allowed(99, 99, -1001, managers)  # посторонний
    assert is_allowed(99, 99, None, frozenset())  # ничего не настроено — открыт для первой настройки


def test_actor_name():
    assert actor_name("Иван", "Петров", "ivan") == "Иван Петров (Telegram)"
    assert actor_name(None, None, "ivan") == "@ivan (Telegram)"
    assert actor_name(None, None, None) == "Менеджер (Telegram)"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/lead 12", 12),
        ("/lead №12", 12),
        ("/lead_12", 12),
        ("/lead_12@smeta_bot", 12),
        ("/lead", None),
        ("/lead abc", None),
        (None, None),
    ],
)
def test_parse_lead_id(text, expected):
    assert parse_lead_id(text) == expected


def test_list_text_and_toast():
    assert "Пусто" in leads_list_text([], 0, "Ждут звонка", SCHEDULE)
    lead = {
        "id": 5,
        "status": "new",
        "name": "Анна",
        "phone": "+79991234567",
        "created_at": "2026-10-24T09:00:00+00:00",
        "estimate": None,
    }
    text = leads_list_text([lead], 1, "Ждут звонка", SCHEDULE)
    assert "/lead_5" in text
    assert "без сметы" in text
    assert status_toast({"id": 5, "status": "won"}, True) == "№5: Договор"
    assert "уже статус" in status_toast({"id": 5, "status": "won"}, False)


# ---------- Клиент API бота против настоящего сайта ----------
@pytest.fixture
def live_site(app):
    """Запускает сайт в отдельном потоке на свободном порту — как в жизни, только локально."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_site_api_client(live_site, client, telegram):
    lead_id = client.post("/api/leads", json=lead_payload()).get_json()["id"]
    api = SiteAPI(live_site, INTERNAL_TOKEN)

    async def scenario():
        new = await api.leads(status="new")
        lead, changed = await api.set_status(lead_id, "quoted", "Анна (Telegram)")
        title, stats = await api.stats("week")
        one = await api.lead(lead_id)
        return new, lead, changed, title, stats, one

    new, lead, changed, title, stats, one = asyncio.run(scenario())
    assert new[0]["id"] == lead_id
    assert (lead["status"], changed) == ("quoted", True)
    assert title == "За 7 дней"
    assert stats["by_status"]["quoted"] == 1
    assert one["estimate"]["total"] == 478_000


def test_site_api_errors(live_site):
    bad = SiteAPI(live_site, "wrong-token")
    with pytest.raises(SiteAPIError) as error:
        asyncio.run(bad.leads())
    assert error.value.status == 401
    nowhere = SiteAPI("http://127.0.0.1:9", INTERNAL_TOKEN, timeout=1)
    with pytest.raises(SiteAPIError, match="Сайт не отвечает"):
        asyncio.run(nowhere.leads())


# ---------- Обработчики aiogram (в CI, где установлен aiogram) ----------
def test_bot_wiring():
    pytest.importorskip("aiogram")
    from bot.__main__ import COMMANDS, create_dispatcher
    from bot.config import BotConfig
    from bot.handlers import markup

    config = BotConfig(token="123:TEST", chat_id=-1001, site_url="http://site", api_token="x")
    dp = create_dispatcher(config, SiteAPI("http://site", "x"))
    assert dp.workflow_data["config"] is config
    assert {c.command for c in COMMANDS} == {"new", "open", "today", "week", "lead", "help"}
    keyboard = markup({"id": 3, "status": "new"})
    assert keyboard.inline_keyboard[0][0].callback_data == "st:3:in_progress"
