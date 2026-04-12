import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import settings, telegram_chat_ids
from engine.analyzer import AnalyzerOrchestrator
from bot.formatter import BotFormatter
from data.broker_fetcher import broker
from data.cache import cache
from db.database import db_instance
from utils.timezone import TimezoneNormalizer

logger = logging.getLogger(__name__)

class EngineScheduler:
    def __init__(self, bot: Bot):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self.bot = bot
        
    async def analyze_and_broadcast(self):
        """Task that runs every minute to analyze NIFTY and broadcast updates."""
        from datetime import time
        # Zero-Resource NSE Block: Prevent API execution off-hours
        now_ist = TimezoneNormalizer.now_ist_aware()
        if now_ist.weekday() > 4: return # Sat/Sun block
        
        current_time = now_ist.time()
        # Aligned with StrategyEngine session (09:30–15:00 IST)
        start_time = time(9, 30)
        end_time = time(15, 0)
        if current_time < start_time or current_time > end_time:
            return # Overnight block

        try:
            # Check for new trading day boundary to reset Halt statuses and Vaporize Stale Caches
            from engine.risk_manager import risk_manager
            flushed = await risk_manager.try_midnight_flush()
            if flushed:
                cache.clear()
                logger.info("Floating 24-hour TTL vaporized purely via Midnight Boundary shift. Cache fully cleared.")

            # Rehydrate instruments master limit once per day
            # We can just call get_instruments, it uses cache inside
            await broker.get_instruments()

            today_ist = TimezoneNormalizer.now_ist_aware().date().isoformat()
            if cache.get("db_prune_ist_date") != today_ist:
                await db_instance.prune_old_rows()
                cache.set("db_prune_ist_date", today_ist, ttl_seconds=86400 * 4)

            alert_chats = telegram_chat_ids()
            dd_alert = await risk_manager.sync_drawdown_from_portfolio()
            if dd_alert:
                logger.warning(dd_alert)
                for chat_id in alert_chats:
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=dd_alert,
                            parse_mode="Markdown",
                        )
                    except Exception as send_err:
                        logger.error(f"Failed to send drawdown alert: {send_err}")
            
            for index in ["NIFTY", "BANKNIFTY"]:
                signal = await AnalyzerOrchestrator.analyze_market(index)
                if signal and alert_chats:
                    msg = BotFormatter.format_signal(signal)
                    for chat_id in alert_chats:
                        try:
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=msg,
                                parse_mode="Markdown",
                            )
                        except Exception as send_err:
                            logger.error(f"Failed to send signal alert: {send_err}")
                elif signal:
                    logger.warning("Signal generated but no TELEGRAM_CHAT_ID configured; alert not sent.")
                    
        except Exception as e:
            logger.error(f"Error in scheduler tick: {e}", exc_info=True)

    def start(self):
        # Run every 60 seconds during market hours
        # For testing, we run strictly on interval
        self.scheduler.add_job(
            self.analyze_and_broadcast,
            "interval",
            seconds=60,
            id="market_analyzer_job",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )
        self.scheduler.start()
        logger.info("Scheduler started.")
