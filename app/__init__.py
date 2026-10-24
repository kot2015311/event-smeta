"""Сайт агентства мероприятий «Смета за минуту».

create_app() — «фабрика приложения»: собирает Flask-приложение из частей.
Так удобно запускать сайт, тесты и команды с разными настройками.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app import db
from app.config import Config
from app.icons import ICONS
from app.notify import TelegramNotifier
from app.security import RateLimiter, csrf_token
from core import statuses
from core.fmt import guests_gen, guests_nom, hours_label, money, num, plural, short_range
from core.leads import CALL_TIMES, CHANNELS
from core.phones import format_phone
from core.pricing import addon_hint, load_default_prices
from core.schedule import local_time

SKINS = {"classic": "Классика", "bright": "Яркая"}


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if app.config["SECRET_KEY"] == "dev-only-secret-change-me" and not app.config.get("TESTING"):
        logging.getLogger(__name__).warning("SECRET_KEY не задан: для настоящего сайта впишите свой в .env")

    # За nginx адрес клиента приходит в заголовке X-Forwarded-For
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    db.init_app(app)

    # Общие объекты приложения: ограничители частоты и отправитель в Telegram
    app.extensions["lead_limiter"] = RateLimiter(app.config["LEAD_RATE_LIMIT"], app.config["LEAD_RATE_WINDOW"])
    app.extensions["login_limiter"] = RateLimiter(5, 15 * 60)  # 5 неверных паролей за 15 минут
    app.extensions["notifier"] = TelegramNotifier(
        token=app.config["TELEGRAM_BOT_TOKEN"],
        chat_id=app.config["TELEGRAM_CHAT_ID"],
        api_url=app.config["TELEGRAM_API_URL"],
        db_path=app.config["DATABASE_PATH"],
        site_url=app.config["SITE_URL"],
        schedule=load_default_prices()["schedule"],
        run_async=app.config["TELEGRAM_ASYNC"],
    )

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_security_headers(app)
    _register_errors(app)

    from app.cli import register_cli

    register_cli(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from app.views import admin, api, internal, site

    app.register_blueprint(site.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(internal.bp)
    app.register_blueprint(admin.bp)


def _asset_version(static_dir: Path) -> str:
    """Короткий хэш содержимого CSS и JS: меняется — браузер скачает файлы заново."""
    digest = hashlib.sha1()
    for path in sorted(static_dir.rglob("*")):
        if path.suffix in {".css", ".js"}:
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def _register_template_helpers(app: Flask) -> None:
    """Фильтры и переменные, доступные во всех шаблонах."""
    env = app.jinja_env
    env.globals.update(
        ICONS=ICONS,
        STATUSES=statuses.STATUSES,
        STATUS_ORDER=statuses.ORDER,
        CHANNELS=CHANNELS,
        CALL_TIMES=CALL_TIMES,
        SKINS=SKINS,
        plural=plural,
        addon_hint=addon_hint,
        csrf_token=csrf_token,
    )
    env.filters.update(
        money=money,
        num=num,
        phone=format_phone,
        guests_nom=guests_nom,
        guests_gen=guests_gen,
        hours_label=hours_label,
        short_range=lambda est: short_range(est["low"], est["high"]),
        status_title=statuses.title,
        dt=lambda value, fmt="%d.%m.%Y %H:%M": local_time(value, "Europe/Moscow", fmt) if value else "",
        percent=lambda value: f"{round(value * 100)}%",
    )
    version = _asset_version(Path(app.static_folder or ""))

    @app.context_processor
    def common_context() -> dict[str, Any]:
        # Стиль сайта: из cookie (переключатель) или из настроек
        skin = request.cookies.get("skin") if app.config["SKIN_SWITCHER"] else None
        if skin not in SKINS:
            skin = app.config["SITE_SKIN"] if app.config["SITE_SKIN"] in SKINS else "classic"
        return {
            "agency": {
                "name": app.config["AGENCY_NAME"],
                "phone": app.config["AGENCY_PHONE"],
                "email": app.config["AGENCY_EMAIL"],
                "telegram": app.config["AGENCY_TELEGRAM"],
                "response_minutes": app.config["RESPONSE_MINUTES"],
            },
            "skin": skin,
            "skin_switcher": app.config["SKIN_SWITCHER"],
            "asset_version": version,
        }


def _register_security_headers(app: Flask) -> None:
    """Заголовки, которые закрывают типовые дыры: встраивание в чужие сайты, чужие скрипты."""
    csp = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )

    @app.after_request
    def add_headers(response):  # type: ignore[no-untyped-def]
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith(("/admin", "/internal", "/api")):
            response.headers.setdefault("Cache-Control", "no-store")  # заявки клиентов не кэшируем
        return response


def _register_errors(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):  # type: ignore[no-untyped-def]
        return render_template("site/error.html", code=404, title="Страница не найдена"), 404

    @app.errorhandler(400)
    def bad_request(error):  # type: ignore[no-untyped-def]
        return render_template("site/error.html", code=400, title=error.description or "Неверный запрос"), 400
