"""Публичный API сайта: смета и приём заявок."""

from __future__ import annotations

from app import repo
from tests.conftest import lead_payload


def test_config(client):
    data = client.get("/api/config").get_json()
    assert {f["id"] for f in data["prices"]["formats"]} >= {"corporate", "business"}


def test_estimate_endpoint(client):
    response = client.post("/api/estimate", json={"format": "corporate", "guests": 80, "level": "standard", "addons": ["host"]})
    data = response.get_json()
    assert response.status_code == 200
    assert data["format"]["id"] == "corporate"
    assert data["lines"][1]["id"] == "host"
    assert "₽" in data["range_text"]


def test_lead_is_saved_and_sent_to_telegram(client, db, telegram):
    response = client.post("/api/leads", json=lead_payload())
    assert response.status_code == 201
    body = response.get_json()
    assert body["ok"] is True
    lead = repo.get_lead(db, body["id"])
    assert lead["name"] == "Анна"
    assert lead["phone"] == "+79991234567"
    assert lead["estimate_total"] == 478_000
    assert lead["status"] == "new"
    # Карточка ушла в Telegram с кнопками, номер сообщения запомнился
    assert telegram.methods() == ["sendMessage"]
    sent = telegram.calls[0][1]
    assert sent["chat_id"] == "-1001"
    assert "Заявка №" in sent["text"]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"st:{body['id']}:in_progress"
    assert repo.get_lead(db, body["id"])["tg_message_id"] == telegram.next_message_id


def test_price_from_browser_is_ignored(client, db):
    """Цену считает сервер: подсунуть «total: 1» не выйдет."""
    payload = lead_payload()
    payload["estimate"] |= {"total": 1, "low": 1, "high": 2}
    body = client.post("/api/leads", json=payload).get_json()
    assert repo.get_lead(db, body["id"])["estimate_low"] == 430_000


def test_lead_without_estimate(client, db):
    body = client.post("/api/leads", json=lead_payload(attach_estimate=False)).get_json()
    lead = repo.get_lead(db, body["id"])
    assert lead["has_estimate"] == 0
    assert lead["estimate"] is None


def test_validation_errors(client, db, telegram):
    response = client.post("/api/leads", json=lead_payload(name="", phone="123", consent=False))
    assert response.status_code == 400
    assert set(response.get_json()["errors"]) == {"name", "phone", "consent"}
    assert repo.list_leads(db)[1] == 0
    assert telegram.calls == []


def test_honeypot_and_speed_trap(client, db):
    """Роботу отвечаем «успешно», но заявку не сохраняем."""
    assert client.post("/api/leads", json=lead_payload(website="http://spam.example")).status_code == 200
    assert client.post("/api/leads", json=lead_payload(elapsed_ms=500)).status_code == 200
    assert repo.list_leads(db)[1] == 0


def test_rate_limit(client, app):
    app.extensions["lead_limiter"].limit = 2
    statuses = [client.post("/api/leads", json=lead_payload()).status_code for _ in range(3)]
    assert statuses == [201, 201, 429]


def test_not_json(client):
    response = client.post("/api/leads", data="name=Анна", content_type="application/x-www-form-urlencoded")
    assert response.status_code == 400


def test_utm_is_saved(client, db):
    body = client.post("/api/leads", json=lead_payload(utm_source="yandex", utm_campaign="newyear")).get_json()
    lead = repo.get_lead(db, body["id"])
    assert (lead["utm_source"], lead["utm_campaign"]) == ("yandex", "newyear")


def test_telegram_failure_does_not_break_lead(client, db, telegram):
    telegram.fail_with = "Forbidden: bot was kicked from the group chat"
    response = client.post("/api/leads", json=lead_payload())
    assert response.status_code == 201
    assert repo.get_lead(db, response.get_json()["id"])["tg_message_id"] is None
