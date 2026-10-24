"""Команды для терминала: flask init-db, flask seed-demo, flask build-demo и другие.

Запуск из папки проекта, например:  flask seed-demo
(имя приложения flask берёт из файла .flaskenv).
"""

from __future__ import annotations

import re
from pathlib import Path

import click
from flask import Flask, render_template

from app import db as dbmod
from app import repo
from app.services import clear_sample_leads, current_prices, seed_sample_leads
from core.pricing import load_default_prices, normalize_params

STATIC = Path(__file__).with_name("static")


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Создать таблицы в базе (если их ещё нет)."""
        dbmod.init_db(app.config["DATABASE_PATH"])
        click.echo(f"База готова: {app.config['DATABASE_PATH']}")

    @app.cli.command("seed-demo")
    @click.option("--count", default=24, show_default=True, help="Сколько тестовых заявок создать")
    def seed_demo(count: int) -> None:
        """Наполнить CRM правдоподобными тестовыми заявками."""
        conn = dbmod.connect(app.config["DATABASE_PATH"])
        try:
            created = seed_sample_leads(conn, count=count)
        finally:
            conn.close()
        click.echo(f"Создано тестовых заявок: {created}. Удалить их: flask clear-samples")

    @app.cli.command("clear-samples")
    def clear_samples() -> None:
        """Удалить тестовые заявки (настоящие не трогает)."""
        conn = dbmod.connect(app.config["DATABASE_PATH"])
        try:
            removed = clear_sample_leads(conn)
        finally:
            conn.close()
        click.echo(f"Удалено тестовых заявок: {removed}")

    @app.cli.command("telegram-test")
    def telegram_test() -> None:
        """Отправить пробное сообщение в чат менеджеров, чтобы проверить токен и TELEGRAM_CHAT_ID."""
        notifier = app.extensions["notifier"]
        if not notifier.enabled:
            raise click.ClickException("Заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в файле .env")
        notifier._call("sendMessage", {"chat_id": notifier.chat_id, "text": "✅ Сайт подключён к этому чату"})
        click.echo("Сообщение отправлено. Проверьте чат в Telegram.")

    @app.cli.command("build-demo")
    @click.option("--out", default="dist/demo", show_default=True, help="Куда положить файлы")
    def build_demo(out: str) -> None:
        """Собрать демо-версию: одна HTML-страница без сервера (для GitHub Pages)."""
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        full, fragment = render_demo(app)
        (target / "index.html").write_text(full, encoding="utf-8")
        (target / "artifact.html").write_text(fragment, encoding="utf-8")
        click.echo(f"Готово: {target / 'index.html'} ({len(full) // 1024} КБ)")


def _minify_css(css: str) -> str:
    """Убираем комментарии и лишние пробелы: демо-страница станет легче."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    return re.sub(r"\s*([{};,>])\s*", r"\1", css).strip()


def render_demo(app: Flask) -> tuple[str, str]:
    """Рендерит главную в режиме демо: прайс по умолчанию, все стили и скрипты внутри страницы."""
    prices = load_default_prices()
    assets = {
        "css": _minify_css((STATIC / "css" / "site.css").read_text(encoding="utf-8")),
        "js": [(STATIC / "js" / name).read_text(encoding="utf-8") for name in ("engine.js", "site.js", "demo.js")],
    }
    from app.views.site import build_page_context  # импорт здесь, чтобы не было циклического импорта

    with app.test_request_context("/"):
        params = normalize_params(None, prices)
        context = build_page_context(prices, params, demo=True)
        # Ссылки на сайт в демо не нужны: в статике нет сервера
        context.update(skin="classic", skin_switcher=True, inline_assets=assets)
        full = render_template("site/index.html", fragment=False, **context)
        # Для просмотра внутри Claude: без html/head/body, заголовок — просто название
        fragment = render_template("site/index.html", fragment=True, page_title=app.config["AGENCY_NAME"], **context)
    return full, fragment


def current_prices_for_cli(app: Flask) -> dict:
    """Текущий прайс с правками из админки (для команд, которым он нужен)."""
    conn = dbmod.connect(app.config["DATABASE_PATH"])
    try:
        return current_prices(conn)
    finally:
        conn.close()


__all__ = ["current_prices_for_cli", "register_cli", "render_demo", "repo"]
