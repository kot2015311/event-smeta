"""Форматирование чисел и слов по-русски: «80 гостей», «1 250 000 ₽», «2 автобуса»."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

# Неразрывный пробел: не даёт переносить «80» и «гостей» на разные строки
NBSP = "\u00a0"


def js_round(x: float) -> int:
    """Округляет как Math.round в JavaScript: половинки всегда вверх.

    Встроенный round() в Python округляет 2.5 до 2 («банковское» округление),
    а браузер округляет до 3. Чтобы сайт и сервер считали одинаково,
    используем своё округление.
    """
    whole = math.floor(x)  # целая часть вниз: 80.5 -> 80
    return int(whole + 1) if x - whole >= 0.5 else int(whole)  # если дробь ≥ 0.5 — вверх


def plural(n: int, one: str, few: str, many: str) -> str:
    """Выбирает форму слова для числа: 1 гость, 2 гостя, 5 гостей."""
    n = abs(int(n)) % 100  # смотрим только на две последние цифры
    last = n % 10  # последняя цифра
    if 10 < n < 20:  # 11–19 всегда «много»: 11 гостей, 14 автобусов
        return many
    if 1 < last < 5:  # 2, 3, 4 (и 22, 34…) — «несколько»
        return few
    if last == 1:  # 1, 21, 101 — «один»
        return one
    return many  # всё остальное: 0, 5–9


def num(n: float) -> str:
    """1250000 -> «1 250 000» (группы разрядов через неразрывный пробел)."""
    return f"{js_round(n):,}".replace(",", NBSP)


def money(n: float) -> str:
    """1250000 -> «1 250 000 ₽»."""
    return num(n) + NBSP + "₽"


def guests_nom(n: int) -> str:
    """Именительный падеж: «1 гость», «2 гостя», «80 гостей»."""
    return f"{n}{NBSP}{plural(n, 'гость', 'гостя', 'гостей')}"


def guests_gen(n: int) -> str:
    """Родительный падеж: «на 1 гостя», «на 80 гостей»."""
    return f"{n}{NBSP}{plural(n, 'гостя', 'гостей', 'гостей')}"


def hours_label(h: int) -> str:
    """«2 часа», «6 часов»."""
    return f"{h}{NBSP}{plural(h, 'час', 'часа', 'часов')}"


def short_range(low: float, high: float) -> str:
    """Короткая вилка для мобильной плашки: «430–540 тыс. ₽» или «1,2–1,5 млн ₽»."""
    if high < 1_000_000:
        return f"{js_round(low / 1000)}–{js_round(high / 1000)}{NBSP}тыс.{NBSP}₽"

    def mln(v: float) -> str:
        # Как toFixed(1) в JS: 1 250 000 -> «1,3». Decimal(float) берёт точное
        # двоичное значение числа, поэтому половинки округляются так же, как в браузере.
        rounded = Decimal(v / 1_000_000).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return str(rounded).replace(".", ",")

    return f"{mln(low)}–{mln(high)}{NBSP}млн{NBSP}₽"
