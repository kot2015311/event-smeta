"""Обработчики aiogram 3: команды и нажатия кнопок."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Message, TelegramObject

from bot.config import BotConfig
from bot.logic import HELP, LEAD_LINK_RE, actor_name, is_allowed, leads_list_text, parse_lead_id, status_toast
from bot.site_api import SiteAPI, SiteAPIError
from core.cards import lead_card, lead_keyboard, parse_callback, stats_text
from core.pricing import load_default_prices

log = logging.getLogger(__name__)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)  # без превью ссылок под карточкой
SCHEDULE = load_default_prices()["schedule"]  # график работы: для подсказки «когда перезвонить»


class ManagersOnly(BaseFilter):
    """Пропускает только менеджеров: чат из TELEGRAM_CHAT_ID и id из MANAGER_IDS."""

    async def __call__(self, event: TelegramObject, config: BotConfig) -> bool:
        if isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message else 0
        elif isinstance(event, Message):
            chat_id = event.chat.id
        else:
            return False
        user = getattr(event, "from_user", None)
        return is_allowed(chat_id, user.id if user else None, config.chat_id, config.manager_ids)


def markup(lead: dict[str, Any]) -> InlineKeyboardMarkup:
    """Кнопки статусов из core.cards (там они описаны словарями) -> объекты aiogram."""
    rows = lead_keyboard(lead["id"], lead["status"])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(**button) for button in row] for row in rows])


def build_router() -> Router:
    router = Router(name="managers")
    router.message.filter(ManagersOnly())
    router.callback_query.filter(ManagersOnly())

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP)

    @router.message(Command("new"))
    async def cmd_new(message: Message, api: SiteAPI) -> None:
        await send_list(message, api, "new", "Ждут звонка")

    @router.message(Command("open"))
    async def cmd_open(message: Message, api: SiteAPI) -> None:
        await send_list(message, api, "open", "Незакрытые заявки")

    @router.message(Command("today"))
    async def cmd_today(message: Message, api: SiteAPI) -> None:
        await send_stats(message, api, "today")

    @router.message(Command("week"))
    async def cmd_week(message: Message, api: SiteAPI) -> None:
        await send_stats(message, api, "week")

    @router.message(Command("lead"))
    @router.message(F.text.regexp(LEAD_LINK_RE))
    async def cmd_lead(message: Message, api: SiteAPI) -> None:
        lead_id = parse_lead_id(message.text)
        if lead_id is None:
            await message.answer("Напишите номер заявки, например: /lead 12")
            return
        try:
            lead = await api.lead(lead_id)
        except SiteAPIError as error:
            await message.answer("Заявка не найдена" if error.status == 404 else f"⚠️ {error}")
            return
        await message.answer(lead_card(lead, SCHEDULE), reply_markup=markup(lead), link_preview_options=NO_PREVIEW)

    @router.callback_query(F.data.startswith("st:"))
    async def on_status(callback: CallbackQuery, api: SiteAPI) -> None:
        parsed = parse_callback(callback.data)
        if parsed is None:
            await callback.answer("Кнопка устарела", show_alert=True)
            return
        lead_id, new_status = parsed
        user = callback.from_user
        try:
            lead, changed = await api.set_status(lead_id, new_status, actor_name(user.first_name, user.last_name, user.username))
        except SiteAPIError as error:
            await callback.answer(f"Не получилось: {error}", show_alert=True)
            return
        await callback.answer(status_toast(lead, changed))
        # Карточку, которую прислал сайт, сайт обновит сам. Остальные (из /lead) обновляем здесь
        message = callback.message
        if isinstance(message, Message) and message.message_id != lead.get("tg_message_id"):
            try:
                await message.edit_text(lead_card(lead, SCHEDULE), reply_markup=markup(lead), link_preview_options=NO_PREVIEW)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error):
                    log.warning("Не удалось обновить карточку №%s: %s", lead_id, error)

    return router


async def send_list(message: Message, api: SiteAPI, status: str, title: str) -> None:
    try:
        leads = await api.leads(status=status, limit=10)
    except SiteAPIError as error:
        await message.answer(f"⚠️ {error}")
        return
    await message.answer(leads_list_text(leads, None, title, SCHEDULE), link_preview_options=NO_PREVIEW)


async def send_stats(message: Message, api: SiteAPI, period: str) -> None:
    try:
        title, stats = await api.stats(period)
    except SiteAPIError as error:
        await message.answer(f"⚠️ {error}")
        return
    await message.answer(stats_text(stats, title))
