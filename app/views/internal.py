"""Служебный API для Telegram-бота.

Бот не ходит в базу напрямую: он просит сайт показать заявки или сменить статус.
Каждый запрос подписан общим секретом в заголовке X-Internal-Token.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request

from app import repo
from app.db import get_db
from app.services import change_status, current_prices
from core import statuses

bp = Blueprint("internal", __name__, url_prefix="/internal")

PERIODS = {"today": "Сегодня", "week": "За 7 дней", "month": "За 30 дней"}


@bp.before_request
def check_token():
    """Пропускаем только запросы с правильным токеном."""
    expected = current_app.config["INTERNAL_API_TOKEN"]
    if not expected:
        return jsonify(ok=False, error="Служебный API выключен: задайте INTERNAL_API_TOKEN в .env"), 503
    sent = request.headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(sent.encode(), expected.encode()):
        return jsonify(ok=False, error="Неверный токен"), 401
    return None


def _public(lead: dict[str, Any]) -> dict[str, Any]:
    """Заявка для ответа API: без сырого JSON сметы (он уже разобран в поле estimate)."""
    return {k: v for k, v in lead.items() if k != "estimate_json"}


@bp.get("/leads")
def leads():
    status = request.args.get("status") or None
    if status and status != "open" and not statuses.is_valid(status):
        return jsonify(ok=False, error="Неизвестный статус"), 400
    limit = min(max(int(request.args.get("limit", 10)), 1), 50)
    rows, total = repo.list_leads(get_db(), status=status, limit=limit)
    return jsonify(ok=True, total=total, leads=[_public(r) for r in rows])


@bp.get("/leads/<int:lead_id>")
def lead(lead_id: int):
    item = repo.get_lead(get_db(), lead_id)
    if item is None:
        return jsonify(ok=False, error="Заявка не найдена"), 404
    return jsonify(ok=True, lead=_public(item))


@bp.post("/leads/<int:lead_id>/status")
def set_status(lead_id: int):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not statuses.is_valid(new_status):
        return jsonify(ok=False, error="Неизвестный статус"), 400
    actor = str(data.get("actor") or "Telegram")[:80]
    item, changed = change_status(get_db(), lead_id, new_status, actor, current_app.extensions["notifier"])
    if item is None:
        return jsonify(ok=False, error="Заявка не найдена"), 404
    return jsonify(ok=True, changed=changed, lead=_public(item))


@bp.get("/stats")
def stats():
    period = request.args.get("period", "today")
    if period not in PERIODS:
        return jsonify(ok=False, error="period: today, week или month"), 400
    db = get_db()
    prices = current_prices(db)
    now = datetime.now(UTC)
    if period == "today":  # с полуночи по Москве
        local = now.astimezone(ZoneInfo(prices["schedule"]["tz"]))
        since = local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since = now - timedelta(days=7 if period == "week" else 30)
    return jsonify(ok=True, title=PERIODS[period], stats=repo.stats(db, prices, since))
