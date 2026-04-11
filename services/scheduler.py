import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import settings
from engine.analyzer import AnalyzerOrchestrator
from bot.formatter import BotFormatter
from data.broker_fetcher import broker

logger = logging.getLogger(__name__)

class EngineScheduler:
    def __init__(self, bot: Bot):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self.bot = bot
        
    async def analyze_and_broadcast(self):
        """Task that runs every minute to analyze NIFTY and broadcast updates."""
        from datetime import time
        from utils.timezone import TimezoneNormalizer
        # Zero-Resource NSE Block: Prevent API execution off-hours
        now_ist = TimezoneNormalizer.now_ist_aware()
        if now_ist.weekday() > 4: return # Sat/Sun block
        
        current_time = now_ist.time()
        start_time = time(9, 15)
        end_time = time(15, 30)
        if current_time < start_time or current_time > end_time:
            return # Overnight block

        try:
            # Check for new trading day boundary to reset Halt statuses and Vaporize Stale Caches
            from engine.risk_manager import risk_manager
            flushed = await risk_manager.try_midnight_flush()
            if flushed:
                from data.cache import cache
                cache.clear()
                logger.info("Floating 24-hour TTL vaporized purely via Midnight Boundary shift. Cache fully cleared.")

            # Rehydrate instruments master limit once per day
            # We can just call get_instruments, it uses cache inside
            await broker.get_instruments()
            
            for index in ["NIFTY", "BANKNIFTY"]:
                signal = await AnalyzerOrchestrator.analyze_market(index)
                if signal:
                    msg = BotFormatter.format_signal(signal)
                    await self.bot.send_message(
                        chat_id=settings.TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode="Markdown"
                    )
                    # If we find a signal, maybe pause short term or continue. 
                    # Assuming we continue analyzing other indices.
                    
        except Exception as e:
            logger.error(f"Error in scheduler tick: {e}", exc_info=True)

    def start(self):
        # Run every 60 seconds during market hours
        # For testing, we run strictly on interval
        self.scheduler.add_job(
            self.analyze_and_broadcast,
            "interval",
            seconds=60,
            id="market_analyzer_job"
        )
        self.scheduler.start()
        logger.info("Scheduler started.")
