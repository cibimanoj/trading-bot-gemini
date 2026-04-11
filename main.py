import asyncio
import logging
from aiogram import Bot, Dispatcher

from config import settings
from db.database import db_instance
from bot.handlers import router
from services.scheduler import EngineScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Quant Options Engine...")

    # 1. Init Database
    await db_instance.init_db()
    
    # 1a. Hydrate Risk State
    from engine.risk_manager import risk_manager
    await risk_manager.hydrate_state()

    # 2. Init Bot
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing in config. Exiting.")
        return

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
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Engine stopped by user.")
