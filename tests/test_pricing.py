"""Расчёт сметы: сверка с первым макетом сайта и правила прайса."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.fmt import guests_gen, guests_nom, js_round, money, plural, short_range
from core.pricing import (
    addon_hint,
    apply_overrides,
    describe,
    estimate,
    load_default_prices,
    normalize_params,
    range_text,
)

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "tests" / "golden_estimates.json").read_text(encoding="utf-8"))


def _short(est: dict) -> dict:
    return {
        "format": est["format"]["id"],
        "level": est["level"]["id"],
        "hours": est["hours"],
        "guests": est["guests"],
        "total": est["total"],
        "low": est["low"],
        "high": est["high"],
        "per_guest": est["per_guest"],
        "lines": [{"id": line["id"], "sum": line["sum"], "note": line["note"]} for line in est["lines"]],
    }


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=[c["name"] for c in GOLDEN["cases"]])
def test_matches_original_calculator(case):
    """Каждая из 400+ смет совпадает с калькулятором первого макета до рубля и до подписи."""
    prices = load_default_prices()
    assert _short(estimate(case["input"], prices)) == case["expected"]


def test_addon_hints_match_original():
    prices = load_default_prices()
    for rule in prices["addons"]:
        assert addon_hint(rule).replace("\u00a0", " ") == GOLDEN["hints"][rule["id"]]


@pytest.mark.skipif(shutil.which("node") is None, reason="нужен Node.js")
def test_js_engine_matches_golden():
    """Браузерный движок (engine.js) считает так же, как Python."""
    result = subprocess.run(["node", "scripts/check_js_engine.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_new_year_example():
    prices = load_default_prices()
    est = estimate(normalize_params(prices["presets"][1]["state"], prices), prices)
    assert est["total"] == 478_000
    assert (est["low"], est["high"]) == (430_000, 540_000)
    assert est["per_guest"] == 6_000
    assert describe(est) == "Корпоратив, уровень «Стандарт», 80\u00a0гостей, 4\u00a0часа"
    assert range_text(est) == "430\u00a0000 – 540\u00a0000\u00a0₽"


def test_normalize_handles_garbage():
    prices = load_default_prices()
    params = normalize_params({"guests": "много", "hours": None, "addons": "host,,fireworks,host", "format": ""}, prices)
    assert params == {"format": "corporate", "guests": 50.0, "hours": 4, "level": "comfort", "addons": ["host"]}


def test_guests_are_clamped():
    prices = load_default_prices()
    assert estimate({"format": "business", "guests": 3}, prices)["guests"] == 10
    assert estimate({"format": "business", "guests": 99999}, prices)["guests"] == 500


def test_overrides_change_price():
    prices = load_default_prices()
    base = estimate({"format": "business", "level": "standard", "guests": 50, "hours": 4, "addons": []}, prices)
    cheaper = apply_overrides(prices, {"formats": {"business": {"min": 20000}}})
    est = estimate({"format": "business", "level": "standard", "guests": 50, "hours": 4, "addons": []}, cheaper)
    assert base["total"] == 30_000
    assert est["total"] == 20_000


def test_overrides_ignore_bad_values():
    prices = load_default_prices()
    bad = {
        "formats": {"business": {"min": "дёшево", "title": "Взлом"}},
        "addons": {"venue": {"price": [1, 2]}, "host": {"price": -5}},
        "range": {"low": True},
        "unknown": {"x": 1},
    }
    assert apply_overrides(prices, bad) == prices


def test_default_prices_are_not_mutated():
    prices = load_default_prices()
    prices["formats"][0]["min"] = 1
    assert load_default_prices()["formats"][0]["min"] == 30000


@pytest.mark.parametrize(
    ("n", "word"),
    [(1, "гость"), (2, "гостя"), (5, "гостей"), (11, "гостей"), (14, "гостей"), (21, "гость"), (22, "гостя"), (111, "гостей")],
)
def test_plural(n, word):
    assert plural(n, "гость", "гостя", "гостей") == word


def test_formatting():
    assert js_round(2.5) == 3  # как в JavaScript, а не «банковское» округление Python
    assert js_round(-0.4) == 0
    assert money(1250000) == "1\u00a0250\u00a0000\u00a0₽"
    assert guests_nom(21) == "21\u00a0гость"
    assert guests_gen(21) == "21\u00a0гостя"
    assert short_range(430000, 540000) == "430–540\u00a0тыс.\u00a0₽"
    assert short_range(1_250_000, 1_550_000) == "1,3–1,6\u00a0млн\u00a0₽"
