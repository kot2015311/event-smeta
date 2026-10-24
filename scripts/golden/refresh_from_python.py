"""Пересобирает эталон tests/golden_estimates.json по текущему prices.json.

Когда нужен: вы намеренно поменяли цены ПО УМОЛЧАНИЮ в core/prices.json
(правки из CRM хранятся в базе и эталон не трогают). После пересборки тесты
по-прежнему проверяют главное: что JS-движок в браузере считает так же, как Python.

Запуск из корня проекта:  python scripts/golden/refresh_from_python.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.pricing import addon_hint, estimate, load_default_prices  # noqa: E402

GOLDEN = ROOT / "tests" / "golden_estimates.json"


def main() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    prices = load_default_prices()
    for case in data["cases"]:
        est = estimate(case["input"], prices)
        case["expected"] = {
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
    data["hints"] = {rule["id"]: addon_hint(rule).replace("\u00a0", " ") for rule in prices["addons"]}
    data["source"] = "Пересобрано по core/prices.json: python scripts/golden/refresh_from_python.py"
    GOLDEN.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Эталон обновлён. Смет в нём: {len(data['cases'])}. Теперь запустите pytest")


if __name__ == "__main__":
    main()
