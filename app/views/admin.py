"""Мини-CRM для менеджера: обзор, заявки, карточка заявки, цены, выгрузка."""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import repo
from app.db import get_db
from app.security import check_csrf, client_ip, csrf_token, login_required, password_ok
from app.services import (
    PRICE_OVERRIDES_KEY,
    change_status,
    current_prices,
    lead_counts_by_status,
)
from core import statuses
from core.leads import CALL_TIMES, CHANNELS
from core.phones import format_phone
from core.pricing import EDITABLE_FIELDS, estimate, load_default_prices, normalize_params

bp = Blueprint("admin", __name__, url_prefix="/admin")

PER_PAGE = 25


# ---------------------------------------------------------------------------
# Вход и выход
# ---------------------------------------------------------------------------


@bp.route("/login", methods=["GET", "POST"])
def login():
    enabled = bool(current_app.config["ADMIN_PASSWORD"])
    error = ""
    limiter = current_app.extensions["login_limiter"]
    ip = client_ip()
    if request.method == "POST" and enabled:
        check_csrf()
        if limiter.blocked(ip):
            error = "Слишком много попыток. Подождите 15 минут и попробуйте снова."
        elif password_ok(request.form.get("password", "")):
            limiter.reset(ip)
            next_url = request.args.get("next", "")
            session.clear()  # новая сессия после входа: защита от подмены сессии
            session["admin"] = True
            session.permanent = True
            csrf_token()  # сразу выдаём новый токен для форм
            # Возвращаем туда, куда человек шёл, но только внутри CRM
            return redirect(next_url if next_url.startswith("/admin") else url_for("admin.dashboard"))
        else:
            limiter.hit(ip)
            error = "Неверный пароль"
    return render_template("admin/login.html", enabled=enabled, error=error), (401 if error else 200)


@bp.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------------------
# Обзор
# ---------------------------------------------------------------------------


def _bars(points: list[tuple[str, int]]) -> dict[str, Any]:
    """Готовит столбики графика «заявки по дням» для SVG в шаблоне."""
    top = max([n for _, n in points] + [1])
    step = 4 if top > 8 else 2 if top > 4 else 1
    ceiling = math.ceil(top / step) * step  # верх шкалы — круглое число
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    bars = []
    for day, count in points:
        date = datetime.fromisoformat(day)
        bars.append(
            {
                "day": date.strftime("%d.%m"),
                "weekday": days[date.weekday()],
                "count": count,
                "share": count / ceiling,
                "weekend": date.weekday() >= 5,
            }
        )
    return {"bars": bars, "ceiling": ceiling, "ticks": list(range(0, ceiling + 1, step))}


@bp.get("/")
@login_required
def dashboard():
    db = get_db()
    prices = current_prices(db)
    now = datetime.now(UTC)
    week = repo.stats(db, prices, now - timedelta(days=7))
    month = repo.stats(db, prices, now - timedelta(days=30))
    chart = _bars(repo.leads_per_day(db, 14, prices["schedule"]["tz"]))
    latest, _ = repo.list_leads(db, limit=6)
    waiting, _ = repo.list_leads(db, status="new", limit=5)
    return render_template(
        "admin/dashboard.html", week=week, month=month, chart=chart, latest=latest, waiting=waiting, nav="dashboard"
    )


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------


def _list_filters() -> dict[str, Any]:
    status = request.args.get("status") or ""
    if status not in ("", "open", *statuses.ORDER):
        status = ""
    return {
        "status": status,
        "format": request.args.get("format") or "",
        "q": (request.args.get("q") or "").strip(),
    }


@bp.get("/leads")
@login_required
def leads():
    db = get_db()
    filters = _list_filters()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    rows, total = repo.list_leads(
        db,
        status=filters["status"] or None,
        format_id=filters["format"] or None,
        q=filters["q"] or None,
        limit=PER_PAGE,
        offset=(page - 1) * PER_PAGE,
    )
    pages = max(math.ceil(total / PER_PAGE), 1)
    return render_template(
        "admin/leads.html",
        leads=rows,
        total=total,
        page=page,
        pages=pages,
        filters=filters,
        counts=lead_counts_by_status(db),
        formats=current_prices(db)["formats"],
        nav="leads",
    )


@bp.get("/leads/<int:lead_id>")
@login_required
def lead(lead_id: int):
    db = get_db()
    item = repo.get_lead(db, lead_id)
    if item is None:
        abort(404)
    return render_template(
        "admin/lead.html",
        lead=item,
        events=repo.lead_events(db, lead_id),
        tg_enabled=current_app.extensions["notifier"].enabled,
        nav="leads",
    )


@bp.post("/leads/<int:lead_id>/status")
@login_required
def lead_status(lead_id: int):
    new_status = request.form.get("status", "")
    if not statuses.is_valid(new_status):
        abort(400, description="Неизвестный статус")
    item, changed = change_status(get_db(), lead_id, new_status, "CRM", current_app.extensions["notifier"])
    if item is None:
        abort(404)
    if changed:
        flash(f"Статус заявки №{lead_id}: {statuses.title(new_status)}")
    return redirect(url_for("admin.lead", lead_id=lead_id))


@bp.post("/leads/<int:lead_id>/note")
@login_required
def lead_note(lead_id: int):
    db = get_db()
    if repo.get_lead(db, lead_id) is None:
        abort(404)
    text = request.form.get("text", "").strip()
    if text:
        repo.add_note(db, lead_id, text, "CRM")
        flash("Заметка сохранена")
    return redirect(url_for("admin.lead", lead_id=lead_id) + "#history")


@bp.get("/leads.csv")
@login_required
def export_csv():
    """Выгрузка в CSV для Excel: точка с запятой и BOM, чтобы кириллица открылась без кракозябр."""
    filters = _list_filters()
    rows, _ = repo.list_leads(
        get_db(),
        status=filters["status"] or None,
        format_id=filters["format"] or None,
        q=filters["q"] or None,
        limit=None,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "№",
            "Создана",
            "Статус",
            "Имя",
            "Телефон",
            "Почта",
            "Telegram",
            "Как связаться",
            "Когда звонить",
            "Формат",
            "Гостей",
            "Часов",
            "Смета от",
            "Смета до",
            "Комментарий",
            "Источник",
        ]
    )
    for r in rows:
        est = r["estimate"] or {}
        writer.writerow(
            [
                r["id"],
                datetime.fromisoformat(r["created_at"]).astimezone().strftime("%d.%m.%Y %H:%M"),
                statuses.title(r["status"]),
                r["name"],
                format_phone(r["phone"]),
                r["email"],
                r["telegram"],
                CHANNELS.get(r["channel"], r["channel"]),
                CALL_TIMES.get(r["call_time"], r["call_time"]),
                est.get("format", {}).get("title", ""),
                r["guests"] or "",
                r["hours"] or "",
                r["estimate_low"] or "",
                r["estimate_high"] or "",
                r["message"],
                r["utm_source"],
            ]
        )
    filename = f"zayavki-{datetime.now():%Y-%m-%d}.csv"
    return Response(
        "﻿" + buffer.getvalue(),  # BOM — подсказка Excel, что файл в UTF-8
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Цены
# ---------------------------------------------------------------------------


def _parse_number(raw: str) -> float | None:
    """«1 500», «0,45» -> число. Пустая строка или мусор -> None."""
    cleaned = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return int(value) if value.is_integer() else value


def _overrides_from_form(form: Any, defaults: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Собирает правки цен из полей формы вида «addons.venue.price.1».

    Сохраняем только то, что отличается от prices.json, — так видно, что именно менял менеджер.
    """
    overrides: dict[str, Any] = {}
    errors: list[str] = []
    for section in ("formats", "levels", "hours", "addons"):
        for item in defaults[section]:
            key = str(item.get("id", item.get("h")))
            for field in EDITABLE_FIELDS[section]:
                default = item.get(field)
                if isinstance(default, list):
                    values = [_parse_number(form.get(f"{section}.{key}.{field}.{i}", "")) for i in range(len(default))]
                    if any(v is None for v in values):
                        errors.append(f"{item.get('title', key)}: заполните все цены числами")
                        continue
                    new: Any = values
                else:
                    raw = form.get(f"{section}.{key}.{field}")
                    if raw is None or (default is None and raw.strip() == ""):
                        continue  # поля нет на форме или оно необязательное
                    new = _parse_number(raw)
                    if new is None:
                        errors.append(f"{item.get('title', item.get('label', key))}: «{raw}» не похоже на число")
                        continue
                if new != default:
                    overrides.setdefault(section, {}).setdefault(key, {})[field] = new
    for field in EDITABLE_FIELDS["range"]:
        new = _parse_number(form.get(f"range.{field}", ""))
        if new is None:
            errors.append("Вилка цены: укажите числа, например 0,9 и 1,12")
        elif new != defaults["range"][field]:
            overrides.setdefault("range", {})[field] = new
    # Здравый смысл: «от» не больше «до», нижняя граница вилки меньше верхней
    for fmt in defaults["formats"]:
        change = overrides.get("formats", {}).get(fmt["id"], {})
        low, high = change.get("min", fmt["min"]), change.get("max", fmt["max"])
        if low > high:
            errors.append(f"{fmt['title']}: цена «от» больше цены «до»")
    rng = defaults["range"] | overrides.get("range", {})
    if rng["low"] >= rng["high"]:
        errors.append("Вилка цены: нижний множитель должен быть меньше верхнего")
    return overrides, errors


def _show(value: Any) -> str:
    """Число для поля ввода: 150000 -> «150 000», 0.45 -> «0,45»."""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:g}".replace(".", ",")
    return f"{int(value):,}".replace(",", " ")


# Подпись под названием услуги: за что именно берётся цена
ADDON_NOTES = {
    "venue": "за гостя",
    "host": "за час работы",
    "show": "за мероприятие",
    "workshop": "за гостя",
    "av": "база плюс цена за каждого гостя сверх 50",
    "design": "за мероприятие",
    "catering": "за гостя",
    "gifts": "за подарок; от 50 штук скидка 10–30%",
    "media": "за мероприятие",
    "transfer": "за автобус на 50 гостей",
    "coord": "за координатора на день, один на 100 гостей",
    "promo": "за час одного человека, один на 40 гостей",
}


def _price_sections(current: dict[str, Any], defaults: dict[str, Any], form: Any) -> list[dict[str, Any]]:
    """Готовит поля формы цен: подпись, имя поля, значение, значение по умолчанию, изменено ли."""
    level_names = [lv["title"] for lv in defaults["levels"]]

    def field(name: str, label: str, value: Any, default: Any, unit: str = "") -> dict[str, Any]:
        shown = form.get(name, "") if form is not None else _show(value)
        return {
            "name": name,
            "label": label,
            "value": shown,
            "unit": unit,
            "default": _show(default) if default is not None else "",
            "changed": default is not None and value != default,
        }

    def by_key(section: str) -> dict[str, dict[str, Any]]:
        return {str(i.get("id", i.get("h"))): i for i in current[section]}

    formats = by_key("formats")
    levels = by_key("levels")
    hours = by_key("hours")
    addons = by_key("addons")

    sections = [
        {
            "id": "formats",
            "title": "Организация и сценарий",
            "hint": "Вилка для 50 гостей и 4 часов. Уровень «Стандарт» берёт нижнюю цену, «Премиум» — верхнюю.",
            "rows": [
                {
                    "title": f["title"],
                    "fields": [
                        field(f"formats.{f['id']}.min", "от", formats[f["id"]]["min"], f["min"], "₽"),
                        field(f"formats.{f['id']}.max", "до", formats[f["id"]]["max"], f["max"], "₽"),
                    ],
                }
                for f in defaults["formats"]
            ],
        },
        {
            "id": "levels",
            "title": "Уровни организации",
            "hint": "Место в вилке формата: 0 — нижняя цена, 1 — верхняя. Множитель удорожает услуги с пометкой «×уровень».",
            "rows": [
                {
                    "title": lv["title"],
                    "fields": [
                        field(f"levels.{lv['id']}.pos", "место в вилке", levels[lv["id"]]["pos"], lv["pos"]),
                        field(f"levels.{lv['id']}.mult", "множитель", levels[lv["id"]]["mult"], lv["mult"], "×"),
                    ],
                }
                for lv in defaults["levels"]
            ],
        },
        {
            "id": "hours",
            "title": "Длительность",
            "hint": "Множитель к организации: 1 — цена за 4 часа.",
            "rows": [
                {"title": d["label"], "fields": [field(f"hours.{d['h']}.k", "множитель", hours[str(d["h"])]["k"], d["k"], "×")]}
                for d in defaults["hours"]
            ],
        },
    ]

    addon_rows = []
    for a in defaults["addons"]:
        now = addons[a["id"]]
        fields = []
        if "base" in a:
            fields.append(field(f"addons.{a['id']}.base", "база", now["base"], a["base"], "₽"))
        if isinstance(a["price"], list):
            for i, name in enumerate(level_names):
                fields.append(field(f"addons.{a['id']}.price.{i}", name, now["price"][i], a["price"][i], "₽"))
        else:
            label = "за гостя сверх 50" if a["id"] == "av" else "цена"
            fields.append(field(f"addons.{a['id']}.price", label, now["price"], a["price"], "₽"))
        if "min" in a:
            fields.append(field(f"addons.{a['id']}.min", "минимум", now["min"], a["min"], "₽"))
        addon_rows.append(
            {
                "title": a["title"],
                "note": ADDON_NOTES.get(a["id"], ""),
                "tag": "×уровень" if a.get("level_mult") else "",
                "fields": fields,
            }
        )
    sections.append(
        {
            "id": "addons",
            "title": "Дополнительные услуги",
            "hint": "Где три цены — своя для каждого уровня. «Минимум» — меньше этой суммы строка сметы не будет.",
            "rows": addon_rows,
        }
    )

    rng = current["range"]
    sections.append(
        {
            "id": "range",
            "title": "Вилка итоговой цены",
            "hint": "Клиент видит итог, умноженный на эти числа: 0,9 — на 10% дешевле, 1,12 — на 12% дороже.",
            "rows": [
                {
                    "title": "Границы вилки",
                    "fields": [
                        field("range.low", "нижняя", rng["low"], defaults["range"]["low"], "×"),
                        field("range.high", "верхняя", rng["high"], defaults["range"]["high"], "×"),
                    ],
                }
            ],
        }
    )
    return sections


@bp.route("/prices", methods=["GET", "POST"])
@login_required
def prices():
    db = get_db()
    defaults = load_default_prices()
    errors: list[str] = []
    if request.method == "POST":
        overrides, errors = _overrides_from_form(request.form, defaults)
        if not errors:
            if overrides:
                repo.set_setting(db, PRICE_OVERRIDES_KEY, overrides)
            else:
                repo.delete_setting(db, PRICE_OVERRIDES_KEY)
            flash("Цены сохранены. Калькулятор на сайте уже считает по-новому.")
            return redirect(url_for("admin.prices"))
    current = current_prices(db)
    examples = [
        {"title": p["title"], "estimate": estimate(normalize_params(p["state"], current), current)} for p in current["presets"]
    ]
    changed = repo.get_setting(db, PRICE_OVERRIDES_KEY) or {}
    return render_template(
        "admin/prices.html",
        sections=_price_sections(current, defaults, request.form if errors else None),
        has_changes=bool(changed),
        errors=errors,
        examples=examples,
        nav="prices",
    ), (400 if errors else 200)


@bp.post("/prices/reset")
@login_required
def prices_reset():
    repo.delete_setting(get_db(), PRICE_OVERRIDES_KEY)
    flash("Цены сброшены к стандартным из prices.json")
    return redirect(url_for("admin.prices"))
