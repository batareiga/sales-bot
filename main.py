#!/usr/bin/env python3
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN
from handlers import router as handlers_router
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    """Set the Telegram menu button commands."""
    from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeChat
    
    cmds = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="data", description="📊 Текущие данные"),
        BotCommand(command="edit", description="✏️ Править категорию"),
        BotCommand(command="send", description="📤 Отправить отчёт"),
        BotCommand(command="reset", description="🔄 Сбросить данные"),
        BotCommand(command="schedule", description="⏰ Расписание отчётов"),
    ]
    
    from config import SALES_GROUP_ID, VADIM_ID
    
    try:
        # Сначала сбрасываем старые команды
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=SALES_GROUP_ID))
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=VADIM_ID))
        
        # Ставим для всех (личные чаты)
        await bot.set_my_commands(cmds, scope=BotCommandScopeDefault())
        logger.info(f"Default commands set: {[c.command for c in cmds]}")
        
        # Ставим для группы продаж
        await bot.set_my_commands(cmds, scope=BotCommandScopeAllGroupChats())
        logger.info(f"Group commands set (all groups)")
        
        # Ставим конкретно для чата продаж и для Вадима
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=SALES_GROUP_ID))
        logger.info(f"Commands set for sales group chat {SALES_GROUP_ID}")
        
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=VADIM_ID))
        logger.info(f"Commands set for Vadim {VADIM_ID}")
        
    except Exception as e:
        logger.error(f"Failed to set commands: {e}", exc_info=True)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(handlers_router)

    await set_commands(bot)
    setup_scheduler(bot)

    logger.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
