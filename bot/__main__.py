"""Запуск бота: python -m bot"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import BotConfig
from bot.handlers import build_router
from bot.site_api import SiteAPI

COMMANDS = [
    BotCommand(command="new", description="Заявки, которые ждут звонка"),
    BotCommand(command="open", description="Все незакрытые заявки"),
    BotCommand(command="today", description="Сводка за сегодня"),
    BotCommand(command="week", description="Сводка за 7 дней"),
    BotCommand(command="lead", description="Карточка заявки: /lead 12"),
    BotCommand(command="help", description="Что умеет бот"),
]


def create_dispatcher(config: BotConfig, api: SiteAPI) -> Dispatcher:
    """Диспетчер с роутером. config и api попадут в обработчики как аргументы (по имени)."""
    dp = Dispatcher(config=config, api=api)
    dp.include_router(build_router())
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = BotConfig.from_env()
    api = SiteAPI(config.site_url, config.api_token)
    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands(COMMANDS)  # меню команд в Telegram
    logging.info("Бот запущен. Сайт: %s", config.site_url)
    # Только сообщения и нажатия кнопок — остальные обновления боту не нужны
    await create_dispatcher(config, api).start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
