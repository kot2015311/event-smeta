"""Публичный API для страницы сайта: прайс, расчёт сметы, приём заявки."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.db import get_db
from app.security import client_ip
from app.services import current_prices, submit_lead
from core.pricing import describe, estimate, normalize_params, range_text

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/config")
def config():
    """Прайс и график работы — всё, что нужно калькулятору в браузере."""
    prices = current_prices(get_db())
    return jsonify(prices=prices)


@bp.post("/estimate")
def calculate():
    """Смета по параметрам. Пример: {"format": "corporate", "guests": 80, "hours": 4,
    "level": "comfort", "addons": ["host", "av"]}"""
    data = request.get_json(silent=True) or {}
    prices = current_prices(get_db())
    est = estimate(normalize_params(data, prices), prices)
    return jsonify(est | {"range_text": range_text(est), "description": describe(est)})


@bp.post("/leads")
def create_lead():
    """Приём заявки с сайта. Ответы: 201 — принята, 400 — ошибки в полях, 429 — слишком часто."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, message="Ожидались данные заявки в формате JSON"), 400
    result = submit_lead(
        get_db(),
        data,
        ip=client_ip(),
        limiter=current_app.extensions["lead_limiter"],
        notifier=current_app.extensions["notifier"],
        min_seconds=current_app.config["LEAD_MIN_SECONDS"],
        response_minutes=current_app.config["RESPONSE_MINUTES"],
    )
    body: dict = {"ok": result.ok, "message": result.message}
    if result.errors:
        body["errors"] = result.errors
    if result.lead_id:
        body["id"] = result.lead_id
    return jsonify(body), result.status
