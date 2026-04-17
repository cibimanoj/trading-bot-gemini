import asyncio
import logging
from aiogram import Bot, Dispatcher

from config import settings, telegram_chat_ids
from db.database import db_instance
from bot.handlers import router
from services.scheduler import EngineScheduler
from utils.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Quant Options Engine...")

    # 1. Init Database
    await db_instance.init_db()
    
    # 1a. Hydrate Risk State
    from engine.risk_manager import risk_manager
    await risk_manager.hydrate_state()
    cap_alert = await risk_manager.sync_drawdown_from_portfolio()
    if cap_alert:
        logger.warning(cap_alert)

    # 2. Init Bot
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing in config. Exiting.")
        return

    if not telegram_chat_ids():
        logger.warning(
            "TELEGRAM_CHAT_ID is empty or has no valid integer ids: "
            "Telegram commands will reject everyone until configured."
        )

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # 3. Start Scheduler
    scheduler = EngineScheduler(bot)
    scheduler.start()

    # 4. Start Bot Polling
    logger.info("Bot is polling...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Engine stopped by user.")
