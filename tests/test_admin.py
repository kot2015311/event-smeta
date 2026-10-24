"""Мини-CRM: вход, заявки, статусы, заметки, выгрузка, цены."""

from __future__ import annotations

from app import repo
from app.services import seed_sample_leads
from tests.conftest import ADMIN_PASSWORD, lead_payload


def create_lead(client, **kw) -> int:
    return client.post("/api/leads", json=lead_payload(**kw)).get_json()["id"]


def test_login_required(client):
    response = client.get("/admin/leads")
    assert response.status_code == 302
    assert "/admin/login?next=/admin/leads" in response.headers["Location"]


def test_wrong_password_and_lockout(client):
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf"]
    for _ in range(5):
        assert client.post("/admin/login", data={"password": "нет", "csrf_token": token}).status_code == 401
    # Шестая попытка блокируется даже с верным паролем
    response = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "csrf_token": token})
    assert "Слишком много попыток" in response.get_data(as_text=True)


def test_login_without_csrf_is_rejected(client):
    client.get("/admin/login")
    assert client.post("/admin/login", data={"password": ADMIN_PASSWORD}).status_code == 400


def test_login_disabled_without_password(app, client):
    app.config["ADMIN_PASSWORD"] = ""
    assert "Вход выключен" in client.get("/admin/login").get_data(as_text=True)


def test_dashboard_and_lists(admin, db):
    seed_sample_leads(db, count=12)
    page = admin.get("/admin/").get_data(as_text=True)
    assert "Заявки по дням" in page
    leads = admin.get("/admin/leads?status=open").get_data(as_text=True)
    assert "Найдено:" in leads
    assert admin.get("/admin/leads?page=99").status_code == 200


def test_search(admin):
    create_lead(admin, name="Зинаида", phone="+7 912 000-11-22")
    create_lead(admin, name="Пётр")
    assert "Зинаида" in admin.get("/admin/leads?q=912000").get_data(as_text=True)
    assert "Пётр" not in admin.get("/admin/leads?q=Зинаида").get_data(as_text=True)


def test_status_change_updates_telegram(admin, db, telegram):
    lead_id = create_lead(admin)
    response = admin.post(f"/admin/leads/{lead_id}/status", data={"status": "won", "csrf_token": admin.csrf})
    assert response.status_code == 302
    lead = repo.get_lead(db, lead_id)
    assert lead["status"] == "won"
    assert lead["status_actor"] == "CRM"
    assert telegram.methods() == ["sendMessage", "editMessageText"]
    assert telegram.calls[1][1]["message_id"] == lead["tg_message_id"]


def test_status_change_requires_csrf(admin):
    lead_id = create_lead(admin)
    assert admin.post(f"/admin/leads/{lead_id}/status", data={"status": "won"}).status_code == 400
    assert admin.post(f"/admin/leads/{lead_id}/status", data={"status": "bad", "csrf_token": admin.csrf}).status_code == 400
    assert admin.post("/admin/leads/999/status", data={"status": "won", "csrf_token": admin.csrf}).status_code == 404


def test_note(admin, db):
    lead_id = create_lead(admin)
    admin.post(f"/admin/leads/{lead_id}/note", data={"text": "Перезвонить в среду", "csrf_token": admin.csrf})
    page = admin.get(f"/admin/leads/{lead_id}").get_data(as_text=True)
    assert "Перезвонить в среду" in page
    assert [e["kind"] for e in repo.lead_events(db, lead_id)] == ["note", "created"]


def test_csv_export(admin):
    create_lead(admin, name="Анна; «кавычки»")
    response = admin.get("/admin/leads.csv")
    text = response.get_data(as_text=True)
    assert response.mimetype == "text/csv"
    assert text.startswith("﻿№;Создана;Статус")
    assert "Корпоратив" in text
    assert '"Анна; «кавычки»"' in text  # точка с запятой внутри поля экранирована


def test_prices_edit_changes_site(admin, client):
    form = admin.get("/admin/prices")
    assert form.status_code == 200
    data = {"csrf_token": admin.csrf, "formats.business.min": "40 000", "range.low": "0,9", "range.high": "1,12"}
    # Остальные поля формы — как были (их отправляет браузер)
    response = admin.post("/admin/prices", data=_full_form(admin, data))
    assert response.status_code == 302
    est = client.post("/api/estimate", json={"format": "business", "level": "standard", "addons": []}).get_json()
    assert est["total"] == 40_000
    assert "было 30 000" in admin.get("/admin/prices").get_data(as_text=True)
    admin.post("/admin/prices/reset", data={"csrf_token": admin.csrf})
    est = client.post("/api/estimate", json={"format": "business", "level": "standard", "addons": []}).get_json()
    assert est["total"] == 30_000


def test_prices_validation(admin):
    response = admin.post("/admin/prices", data=_full_form(admin, {"formats.business.min": "дорого", "range.low": "2"}))
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "не похоже на число" in page
    assert "нижний множитель должен быть меньше" in page


def _full_form(admin, changes: dict) -> dict:
    """Собирает все поля формы цен со страницы и подменяет нужные."""
    import re

    html = admin.get("/admin/prices").get_data(as_text=True)
    fields = dict(re.findall(r'name="([a-z_]+\.[\w.]+)" type="text" inputmode="decimal" value="([^"]*)"', html))
    fields["csrf_token"] = admin.csrf
    fields.update(changes)
    return fields


def test_logout(admin):
    admin.post("/admin/logout", data={"csrf_token": admin.csrf})
    assert admin.get("/admin/").status_code == 302
