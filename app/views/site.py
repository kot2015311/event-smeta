"""Публичная часть: главная с калькулятором, заявка без JavaScript, служебные страницы."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, render_template, request, url_for

from app.content import page_texts
from app.db import get_db
from app.security import client_ip
from app.services import current_prices, submit_lead
from core.pricing import addon_hint, describe, estimate, normalize_params, range_text
from core.schedule import status_text, work_status

bp = Blueprint("site", __name__)

# Короткие имена параметров в ссылке на смету: /?f=corporate&g=80&h=4&l=comfort&a=host,av
QUERY_KEYS = {"f": "format", "g": "guests", "h": "hours", "l": "level", "a": "addons"}


def params_from_args(args: Any) -> dict[str, Any] | None:
    """Достаёт параметры сметы из адресной строки или из формы калькулятора."""
    if not any(key in args for key in QUERY_KEYS) and "calc" not in args:
        return None  # ничего не передали — покажем смету по умолчанию
    raw: dict[str, Any] = {QUERY_KEYS[k]: args.get(k) for k in ("f", "g", "h", "l") if args.get(k)}
    # Услуги приходят либо одной строкой «host,av», либо галочками a=host&a=av
    addons: list[str] = []
    for value in args.getlist("a"):
        addons += [a for a in value.split(",") if a]
    if addons or "calc" in args:  # форма отправлена, но галочек нет — значит, без услуг
        raw["addons"] = addons
    return raw


def structured_data(prices: dict[str, Any], texts: dict[str, Any], site_url: str) -> dict[str, Any]:
    """Разметка schema.org для поисковиков: кто мы, часы работы и ответы на вопросы."""
    sched = prices["schedule"]
    agency = {
        "@type": "ProfessionalService",
        "name": current_app.config["AGENCY_NAME"],
        "description": "Организация корпоративов, конференций, выездных мероприятий и тимбилдингов",
        "telephone": current_app.config["AGENCY_PHONE"],
        "email": current_app.config["AGENCY_EMAIL"],
        "priceRange": f"от {min(f['min'] for f in prices['formats'])} ₽",
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": days, "opens": f"{start:02d}:00", "closes": f"{end:02d}:00"}
            for days, (start, end) in (
                (["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], sched["weekday"]),
                (["Saturday", "Sunday"], sched["weekend"]),
            )
        ],
    }
    if site_url:
        agency["url"] = site_url + "/"
    faq = {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in texts["faq"]
        ],
    }
    return {"@context": "https://schema.org", "@graph": [agency, faq]}


def build_page_context(
    prices: dict[str, Any],
    params: dict[str, Any],
    *,
    demo: bool = False,
    now: datetime | None = None,
    utm: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Всё, что нужно шаблону главной. Используется и сайтом, и сборкой демо-версии."""
    est = estimate(params, prices)
    presets = [
        {**preset, "estimate": estimate(normalize_params(preset["state"], prices), prices)} for preset in prices["presets"]
    ]
    sample = next(p for p in presets if p["id"] == "new-year")  # пример сметы в первом экране
    status = work_status(now, prices["schedule"])
    formats_min = min(f["min"] for f in prices["formats"])
    texts = page_texts(current_app.config["RESPONSE_MINUTES"])
    return {
        "texts": texts,
        "structured_data": structured_data(prices, texts, current_app.config["SITE_URL"]),
        "utm": utm or {},
        "privacy_url": "#privacy" if demo else url_for("site.privacy"),
        "year": (now or datetime.now()).year,
        "prices": prices,
        "params": params,
        "est": est,
        "est_range": range_text(est),
        "est_text": describe(est),
        "presets": presets,
        "sample": sample,
        "addons": [{**a, "hint": addon_hint(a)} for a in prices["addons"]],
        "status": status,
        "status_text": status_text(status),
        "formats_min": formats_min,
        "demo": demo,
        "app_config": {
            "demo": demo,
            "prices": prices,
            "initial": params,
            "endpoints": {} if demo else {"leads": url_for("api.create_lead")},
            "responseMinutes": current_app.config["RESPONSE_MINUTES"],
            "repoUrl": current_app.config["DEMO_REPO_URL"],
        },
    }


@bp.get("/")
def index() -> str:
    prices = current_prices(get_db())
    params = normalize_params(params_from_args(request.args), prices)
    utm = {k: request.args.get(k, "")[:100] for k in ("utm_source", "utm_medium", "utm_campaign")}
    return render_template("site/index.html", **build_page_context(prices, params, utm=utm))


@bp.post("/lead")
def lead_form() -> tuple[str, int]:
    """Запасной путь для браузеров без JavaScript: обычная отправка формы."""
    form = request.form
    payload: dict[str, Any] = {
        key: form.get(key, "")
        for key in (
            "name",
            "phone",
            "email",
            "telegram",
            "channel",
            "call_time",
            "message",
            "website",
            "utm_source",
            "utm_medium",
            "utm_campaign",
        )
    }
    payload["consent"] = form.get("consent")
    payload["attach_estimate"] = form.get("attach_estimate")
    raw = params_from_args(form)
    if raw:
        payload["estimate"] = raw
    result = submit_lead(
        get_db(),
        payload,
        ip=client_ip(),
        limiter=current_app.extensions["lead_limiter"],
        notifier=current_app.extensions["notifier"],
        min_seconds=0,  # без JavaScript время заполнения не измерить
        response_minutes=current_app.config["RESPONSE_MINUTES"],
    )
    return render_template("site/lead_result.html", result=result), result.status


@bp.get("/privacy")
def privacy() -> str:
    return render_template("site/privacy.html")


@bp.get("/robots.txt")
def robots() -> Response:
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    body = "\n".join(
        [
            "User-agent: *",
            "Disallow: /admin/",
            "Disallow: /internal/",
            "Disallow: /api/",
            f"Sitemap: {base}/sitemap.xml",
            "",
        ]
    )
    return Response(body, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap() -> Response:
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    urls = [base + url_for("site.index"), base + url_for("site.privacy")]
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return Response(xml, mimetype="application/xml")


@bp.get("/healthz")
def healthz() -> Response:
    """Проверка «сайт жив» для Docker и мониторинга."""
    get_db().execute("SELECT 1")
    return jsonify(ok=True)
