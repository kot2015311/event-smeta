"""Уведомления в Telegram через Bot API.

Сайт сам отправляет карточку новой заявки в чат менеджеров и обновляет её,
когда меняется статус (в CRM или кнопкой в Telegram). Боту для этого
не нужно ничего знать о базе — он только нажимает кнопки через API сайта.

Отправка идёт в фоне: клиент видит «Заявка принята» сразу,
даже если Telegram отвечает медленно или недоступен.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import requests

from app import db as dbmod
from app import repo
from core.cards import lead_card, lead_keyboard

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Отправляет и обновляет карточки заявок в чате менеджеров."""

    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        api_url: str,
        db_path: str,
        site_url: str,
        schedule: dict[str, Any],
        run_async: bool = True,
        http: Any = requests,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.api_url = api_url.rstrip("/")
        self.db_path = db_path
        self.site_url = site_url
        self.schedule = schedule
        self.run_async = run_async
        self.http = http  # в тестах сюда подставляется заглушка вместо requests

    @property
    def enabled(self) -> bool:
        """Уведомления работают, только если заданы токен бота и чат."""
        return bool(self.token and self.chat_id)

    # --- публичные методы, их вызывает app/services.py ---

    def lead_created(self, lead: dict[str, Any]) -> None:
        """Новая заявка: отправить карточку с кнопками статусов."""
        if self.enabled:
            self._run(self._send_new, lead)

    def lead_updated(self, lead: dict[str, Any]) -> None:
        """Статус изменился: обновить уже отправленную карточку."""
        if self.enabled and lead.get("tg_message_id"):
            self._run(self._edit, lead)

    # --- внутренняя кухня ---

    def _run(self, func, lead: dict[str, Any]) -> None:
        """Запускает отправку в отдельном потоке (или сразу — в тестах)."""
        if self.run_async:
            threading.Thread(target=self._safe, args=(func, lead), daemon=True).start()
        else:
            self._safe(func, lead)

    def _safe(self, func, lead: dict[str, Any]) -> None:
        """Ошибка Telegram не должна ронять сайт: записываем в лог и идём дальше."""
        try:
            func(lead)
        except Exception:  # сюда попадает всё: сеть, неверный токен, лимиты Telegram
            log.exception("Не удалось отправить заявку №%s в Telegram", lead.get("id"))

    def _crm_url(self, lead_id: int) -> str | None:
        return f"{self.site_url}/admin/leads/{lead_id}" if self.site_url else None

    def _message(self, lead: dict[str, Any]) -> dict[str, Any]:
        """Текст и кнопки карточки — одинаковые для отправки и обновления."""
        return {
            "chat_id": self.chat_id,
            "text": lead_card(lead, self.schedule),
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "reply_markup": {"inline_keyboard": lead_keyboard(lead["id"], lead["status"], self._crm_url(lead["id"]))},
        }

    def _send_new(self, lead: dict[str, Any]) -> None:
        result = self._call("sendMessage", self._message(lead))
        # Запоминаем номер сообщения: по нему потом обновим статус в карточке.
        # Поток фоновый, поэтому открываем своё подключение к базе.
        conn = dbmod.connect(self.db_path)
        try:
            repo.set_tg_message_id(conn, lead["id"], int(result["message_id"]))
        finally:
            conn.close()

    def _edit(self, lead: dict[str, Any]) -> None:
        payload = self._message(lead) | {"message_id": lead["tg_message_id"]}
        try:
            self._call("editMessageText", payload)
        except TelegramError as error:
            # Telegram ругается, если текст не изменился, — это не ошибка
            if "message is not modified" not in str(error):
                raise

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Один запрос к Bot API. Возвращает поле result из ответа."""
        response = self.http.post(f"{self.api_url}/bot{self.token}/{method}", json=payload, timeout=10)
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", f"HTTP {response.status_code}"))
        return data["result"]


class TelegramError(RuntimeError):
    """Telegram ответил ошибкой (неверный токен, бот не добавлен в чат и т. п.)."""
