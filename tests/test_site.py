"""Страницы сайта: главная, форма без JavaScript, служебные адреса, заголовки безопасности."""

from __future__ import annotations

import json
import re

from app import repo


def test_index_renders_calculator(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Соберите смету" in html
    assert 'name="f" value="corporate" checked' in html  # формат по умолчанию
    assert "395\u00a0000 – 490\u00a0000" in html  # смета по умолчанию посчитана сервером
    config = json.loads(re.search(r'<script id="app-config" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert config["demo"] is False
    assert config["endpoints"]["leads"] == "/api/leads"


def test_index_reads_estimate_from_link(client):
    html = client.get("/?f=business&g=120&h=6&l=premium&a=host,media").get_data(as_text=True)
    assert 'name="f" value="business" checked' in html
    assert 'name="l" value="premium" checked' in html
    assert 'name="a" value="media" checked' in html
    assert 'name="a" value="catering" checked' not in html


def test_calc_form_without_addons_means_no_addons(client):
    html = client.get("/?calc=1&f=team&g=40&h=2&l=standard").get_data(as_text=True)
    assert 'name="a" value="host" checked' not in html


def test_structured_data_for_search_engines(client):
    html = client.get("/").get_data(as_text=True)
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    types = {node["@type"] for node in data["@graph"]}
    assert types == {"ProfessionalService", "FAQPage"}


def test_lead_form_without_javascript(client, db):
    form = {
        "name": "Олег",
        "phone": "8 999 765 43 21",
        "channel": "phone",
        "call_time": "day",
        "consent": "1",
        "attach_estimate": "1",
        "calc": "1",
        "f": "offsite",
        "g": "40",
        "h": "8",
        "l": "standard",
        "a": "workshop,catering",
    }
    response = client.post("/lead", data=form)
    assert response.status_code == 201
    assert "Заявка принята" in response.get_data(as_text=True)
    lead = repo.list_leads(db)[0][0]
    assert lead["format_id"] == "offsite"
    assert lead["estimate"]["addons"] == ["workshop", "catering"]


def test_lead_form_errors_without_javascript(client):
    response = client.post("/lead", data={"name": "", "phone": ""})
    assert response.status_code == 400
    assert "Укажите имя" in response.get_data(as_text=True)


def test_service_pages(client):
    assert client.get("/privacy").status_code == 200
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /admin/" in robots
    assert "Sitemap: https://smeta.example.ru/sitemap.xml" in robots
    assert "<loc>https://smeta.example.ru/</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    assert client.get("/healthz").get_json() == {"ok": True}
    assert client.get("/nope").status_code == 404


def test_security_headers(client):
    headers = client.get("/").headers
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/config").headers["Cache-Control"] == "no-store"


def test_skin_cookie(client):
    assert 'data-skin="classic"' in client.get("/").get_data(as_text=True)
    client.set_cookie("skin", "bright")
    assert 'data-skin="bright"' in client.get("/").get_data(as_text=True)
    client.set_cookie("skin", "<script>")
    assert 'data-skin="classic"' in client.get("/").get_data(as_text=True)
