"""Команды терминала и сборка демо-версии."""

from __future__ import annotations

import json
import re

from app import repo
from app.cli import render_demo


def test_seed_and_clear(app, db):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo", "--count", "10"])
    assert "Создано тестовых заявок: 10" in result.output
    leads, total = repo.list_leads(db, limit=None)
    assert total == 10
    assert all(lead["source"] == "sample" for lead in leads)
    assert {lead["status"] for lead in leads} - {"new"}, "часть тестовых заявок уже в работе"
    result = runner.invoke(args=["clear-samples"])
    assert "Удалено тестовых заявок: 10" in result.output
    assert repo.list_leads(db)[1] == 0


def test_demo_is_self_contained(app):
    full, fragment = render_demo(app)
    assert full.startswith("<!doctype html>")
    assert "<html" not in fragment and "<body>" not in fragment
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in fragment
    for html in (full, fragment):
        # Все скрипты внутри страницы, внешних нет; стили тоже встроены
        assert not re.search(r"<script[^>]+src=", html)
        assert "/static/" not in html
        assert "window.SmetaDemo" in html
        config = json.loads(re.search(r'<script id="app-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        assert config["demo"] is True
        assert config["endpoints"] == {}


def test_build_demo_command(app, tmp_path):
    result = app.test_cli_runner().invoke(args=["build-demo", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")
