"""Безопасность: вход в CRM, защита форм (CSRF), ограничение частоты запросов."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Any

from flask import abort, current_app, redirect, request, session, url_for


class RateLimiter:
    """Не больше limit событий за window секунд с одного ключа (например, IP).

    Хранит отметки времени в памяти процесса. Для небольшого сайта этого хватает;
    если сайт вырастет до нескольких серверов — счётчики переносят в Redis.
    """

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # gunicorn может обслуживать запросы в нескольких потоках

    def _trim(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:  # выкидываем старые отметки
            hits.popleft()
        return hits

    def allow(self, key: str, now: float | None = None) -> bool:
        """Можно ли сейчас? Если да — сразу засчитывает попытку."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._trim(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def blocked(self, key: str, now: float | None = None) -> bool:
        """Проверка без засчитывания попытки (для входа в CRM)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            return len(self._trim(key, now)) >= self.limit

    def hit(self, key: str, now: float | None = None) -> None:
        """Засчитать попытку (например, неверный пароль)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._trim(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


def client_ip() -> str:
    """IP клиента. За прокси его подставляет ProxyFix (настройка TRUST_PROXY)."""
    return request.remote_addr or "unknown"


# ---------------------------------------------------------------------------
# CSRF: подпись форм, чтобы чужой сайт не мог нажать кнопку в CRM за менеджера
# ---------------------------------------------------------------------------


def csrf_token() -> str:
    """Токен для скрытого поля формы. Живёт в сессии менеджера."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf() -> None:
    """Сравнивает токен из формы с токеном в сессии. Не совпал — ошибка 400."""
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Форма устарела. Обновите страницу и попробуйте ещё раз.")


# ---------------------------------------------------------------------------
# Вход в CRM
# ---------------------------------------------------------------------------


def password_ok(given: str) -> bool:
    """Сравнение пароля за постоянное время (защита от подбора по таймингам)."""
    expected = current_app.config.get("ADMIN_PASSWORD", "")
    if not expected:  # пароль не задан — вход закрыт
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def login_required(view: Any) -> Any:
    """Декоратор: пускает в CRM только после входа, POST-запросы проверяет на CSRF."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.path))
        if request.method == "POST":
            check_csrf()
        return view(*args, **kwargs)

    return wrapper
