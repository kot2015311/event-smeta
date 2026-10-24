"""Российские номера телефонов: проверка и красивый вид."""

from __future__ import annotations

import re


def normalize_phone(raw: str | None) -> str | None:
    """Приводит номер к виду +79991234567. Если номер неполный — возвращает None.

    Принимает любые варианты записи: «8 (999) 123-45-67», «+7 999 1234567», «9991234567».
    """
    digits = re.sub(r"\D", "", raw or "")  # оставляем только цифры
    if len(digits) == 10:  # без кода страны: 9991234567
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":  # 8 в начале меняем на 7
        return "+7" + digits[1:]
    return None


def format_phone(phone: str | None) -> str:
    """+79991234567 -> «+7 (999) 123-45-67». Непонятные строки отдаёт как есть."""
    normalized = normalize_phone(phone)
    if not normalized:
        return phone or ""
    d = normalized[2:]  # 10 цифр после +7
    return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
