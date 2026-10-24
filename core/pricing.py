"""Движок расчёта сметы.

Цены лежат в prices.json, а здесь — только правила, как из них получить смету.
Ровно те же правила повторены в app/static/js/engine.js, чтобы браузер
показывал цену мгновенно. Тест tests/test_pricing.py сверяет обе версии
с эталонными сметами из первого макета сайта (tests/golden_estimates.json).
"""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.fmt import guests_gen, guests_nom, hours_label, js_round, money, num, plural

# Файл с прайсом по умолчанию лежит рядом с этим модулем
PRICES_PATH = Path(__file__).with_name("prices.json")


# ---------------------------------------------------------------------------
# Загрузка прайса
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _read_default_prices() -> dict[str, Any]:
    """Читает prices.json один раз за запуск (результат кэшируется)."""
    with PRICES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_default_prices() -> dict[str, Any]:
    """Отдаёт копию прайса, чтобы случайная правка не испортила кэш."""
    return copy.deepcopy(_read_default_prices())


# Какие числа менеджер может править в админке: раздел -> поля.
# Всё остальное (названия, иконки, формулы) меняется только в prices.json.
EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "formats": ("min", "max"),
    "levels": ("pos", "mult"),
    "hours": ("k",),
    "addons": ("price", "base", "min"),
    "range": ("low", "high"),
}


def apply_overrides(prices: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Накладывает правки из админки на прайс по умолчанию.

    overrides выглядит так:
        {"formats": {"corporate": {"min": 160000}},
         "addons": {"venue": {"price": [900, 1500, 2700]}},
         "range": {"low": 0.85}}
    Неизвестные ключи и нечисловые значения молча пропускаем — это защита
    от «битых» данных в базе.
    """
    result = copy.deepcopy(prices)
    if not overrides:
        return result

    # Простые разделы-списки: ищем элемент по id (у длительности — по числу часов)
    for section in ("formats", "levels", "hours", "addons"):
        changes = overrides.get(section) or {}
        for item in result.get(section, []):
            key = str(item.get("id", item.get("h")))  # у длительности нет id, только h
            for field, value in (changes.get(key) or {}).items():
                if field in EDITABLE_FIELDS[section] and _same_shape(item.get(field), value):
                    item[field] = value

    # Вилка цены — отдельный словарь
    for field, value in (overrides.get("range") or {}).items():
        if field in EDITABLE_FIELDS["range"] and _is_number(value):
            result["range"][field] = value
    return result


def _is_number(value: Any) -> bool:
    """True для int/float, но не для True/False (bool в Python — тоже int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _same_shape(old: Any, new: Any) -> bool:
    """Проверяет, что новое значение того же вида: число вместо числа, список из 3 чисел вместо такого же списка."""
    if isinstance(old, list):
        return isinstance(new, list) and len(new) == len(old) and all(_is_number(v) and v >= 0 for v in new)
    if old is None:  # поле не задано в прайсе (например, base у ведущего) — разрешаем число
        return _is_number(new) and new >= 0
    return _is_number(new) and new >= 0


# ---------------------------------------------------------------------------
# Входные параметры
# ---------------------------------------------------------------------------


def normalize_params(raw: dict[str, Any] | None, prices: dict[str, Any]) -> dict[str, Any]:
    """Приводит параметры от пользователя к понятному виду.

    Откуда угодно (JSON, ссылка, форма) могут прийти строки, пустые значения
    или мусор. Здесь всё превращается в корректный набор:
    формат, число гостей, часы, уровень и список услуг.
    """
    raw = raw or {}
    defaults = prices["defaults"]

    # Число гостей: берём число, иначе значение по умолчанию
    try:
        guests = float(raw.get("guests", defaults["guests"]))
        if not math.isfinite(guests):
            raise ValueError
    except (TypeError, ValueError):
        guests = float(defaults["guests"])

    # Часы: целое число, иначе по умолчанию
    try:
        hours = int(raw.get("hours", defaults["hours"]))
    except (TypeError, ValueError):
        hours = defaults["hours"]

    # Услуги: принимаем список или строку «host,av», оставляем только известные id
    addons_raw = raw.get("addons", defaults["addons"])
    if isinstance(addons_raw, str):
        addons_raw = [a for a in addons_raw.split(",") if a]
    known_addons = {a["id"] for a in prices["addons"]}
    addons = [a for a in addons_raw if isinstance(a, str) and a in known_addons] if isinstance(addons_raw, list) else []

    return {
        "format": str(raw.get("format") or defaults["format"]),
        "guests": guests,
        "hours": hours,
        "level": str(raw.get("level") or defaults["level"]),
        "addons": list(dict.fromkeys(addons)),  # убираем повторы, сохраняя порядок
    }


# ---------------------------------------------------------------------------
# Расчёт
# ---------------------------------------------------------------------------


def _round_500(value: float) -> int:
    """Строки сметы округляем до 500 ₽ — так смета выглядит аккуратно."""
    return js_round(value / 500) * 500


def _nice(value: float) -> int:
    """Красиво округляет границы вилки: чем больше сумма, тем крупнее шаг."""
    if value < 100_000:
        step = 1_000
    elif value < 500_000:
        step = 5_000
    elif value < 2_000_000:
        step = 10_000
    else:
        step = 50_000
    return js_round(value / step) * step


def _units(rule: dict[str, Any], guests: int, hours: int) -> tuple[float, int]:
    """Сколько «единиц» услуги нужно: гостей, часов, автобусов, человеко-часов.

    Возвращает (количество для цены, число групп для подписи).
    """
    unit = rule.get("unit", "event")
    if unit == "event":  # одна услуга на всё мероприятие
        return 1, 1
    if unit == "guest":  # за каждого гостя сверх включённых
        return max(0, guests - rule.get("included", 0)), 1
    if unit == "hour":  # за каждый час
        return hours, 1
    # Группы: автобус на 50 гостей, координатор на 100 гостей и т. п.
    groups = max(rule.get("min_groups", 1), math.ceil(guests / rule["group_size"]))
    if unit == "group":
        return groups, groups
    if unit == "staff_hour":  # люди × часы (промоперсонал)
        return groups * hours, groups
    raise ValueError(f"Неизвестная единица услуги: {unit}")


def _discount(rule: dict[str, Any], guests: int) -> float:
    """Скидка за объём: первое подходящее правило [порог, доля]."""
    for threshold, rate in rule.get("discounts", []):
        if guests >= threshold:
            return rate
    return 0.0


def _note(rule: dict[str, Any], level_index: int, guests: int, hours: int, groups: int, discount: float) -> str:
    """Подпись под строкой сметы: «на 80 гостей», «2 автобуса, туда и обратно»."""
    template = rule.get("note", "")
    if isinstance(template, list):  # своя подпись для каждого уровня
        return template[level_index]
    words = rule.get("words")
    return template.format(
        h=hours,
        g=guests,
        guests=guests_gen(guests),
        n=groups,
        n_word=plural(groups, *words) if words else "",
        discount=f" · скидка {js_round(discount * 100)}%" if discount else "",
    )


def addon_price(rule: dict[str, Any], level_index: int) -> float:
    """Цена за единицу на выбранном уровне (одно число или своя для каждого уровня)."""
    price = rule["price"]
    return price[level_index] if isinstance(price, list) else price


def addon_hint(rule: dict[str, Any]) -> str:
    """Подсказка на карточке услуги: «от 800 ₽/гость», «от 30 000 ₽»."""
    start = rule.get("base") or addon_price(rule, 0)
    return f"от {money(start)}{rule.get('hint_unit', '')}"


def estimate(params: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
    """Считает смету. params — результат normalize_params().

    Логика та же, что у калькулятора из первого макета:
    1) «Организация и сценарий»: вилка формата + сдвиг по уровню,
       растёт с числом гостей (степень 0.7 — чем больше гостей, тем дешевле каждый)
       и с длительностью;
    2) отмеченные услуги по своим формулам;
    3) итог, вилка ±10% и цена на гостя.
    """
    formats = {f["id"]: f for f in prices["formats"]}
    fmt = formats.get(params.get("format")) or formats[prices["defaults"]["format"]]

    # Неизвестный уровень -> самый простой (как в исходном калькуляторе)
    level_index = next((i for i, lv in enumerate(prices["levels"]) if lv["id"] == params.get("level")), 0)
    level = prices["levels"][level_index]

    hours_map = {d["h"]: d for d in prices["hours"]}
    duration = hours_map.get(params.get("hours")) or hours_map[prices["defaults"]["hours"]]

    cfg = prices["guests"]
    guests = min(cfg["max"], max(cfg["min"], js_round(params.get("guests", prices["defaults"]["guests"]))))

    # Чем больше гостей, тем больше работы, но не линейно
    scale = 1 if guests <= cfg["base"] else (guests / cfg["base"]) ** cfg["exponent"]
    base_sum = max(fmt["min"], (fmt["min"] + (fmt["max"] - fmt["min"]) * level["pos"]) * scale * duration["k"])

    lines = [
        {
            "id": "base",
            "title": "Организация и сценарий",
            "note": f"{fmt['title']} · {level['title']}",
            "sum": _round_500(base_sum),
        }
    ]

    chosen = set(params.get("addons") or [])
    for rule in prices["addons"]:  # идём в порядке прайса, чтобы смета всегда выглядела одинаково
        if rule["id"] not in chosen:
            continue
        qty, groups = _units(rule, guests, duration["h"])
        total = rule.get("base", 0) + addon_price(rule, level_index) * qty
        if rule.get("level_mult"):  # дороже на уровнях «Комфорт» и «Премиум»
            total *= level["mult"]
        discount = _discount(rule, guests)
        total *= 1 - discount
        total = max(rule.get("min", 0), total)  # минимальный заказ
        lines.append(
            {
                "id": rule["id"],
                "title": rule["title"],
                "note": _note(rule, level_index, guests, duration["h"], groups, discount),
                "sum": _round_500(total),
            }
        )

    total = sum(line["sum"] for line in lines)
    rng = prices["range"]
    return {
        "format": {"id": fmt["id"], "title": fmt["title"]},
        "level": {"id": level["id"], "title": level["title"]},
        "hours": duration["h"],
        "guests": guests,
        "addons": [line["id"] for line in lines[1:]],
        "lines": lines,
        "total": total,
        "low": max(_nice(total * rng["low"]), fmt["min"]),
        "high": _nice(total * rng["high"]),
        "per_guest": js_round(total / guests / 100) * 100,
    }


def describe(est: dict[str, Any]) -> str:
    """Короткое описание сметы для людей: «Корпоратив, уровень «Комфорт», 80 гостей, 4 часа»."""
    return (
        f"{est['format']['title']}, уровень «{est['level']['title']}», {guests_nom(est['guests'])}, {hours_label(est['hours'])}"
    )


def range_text(est: dict[str, Any]) -> str:
    """«430 000 – 540 000 ₽»."""
    return f"{num(est['low'])} – {money(est['high'])}"
