import asyncio
import logging
from datetime import datetime
import pandas as pd
from kiteconnect import KiteConnect
from tenacity import retry, wait_exponential, stop_after_attempt

from config import settings
from data.cache import cache
from utils.timezone import TimezoneNormalizer

logger = logging.getLogger(__name__)

class BrokerFetcher:
    def __init__(self):
        self.kite = KiteConnect(api_key=settings.KITE_API_KEY)
        if settings.KITE_ACCESS_TOKEN:
            self.kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        self._semaphore = None
        
    @property
    def semaphore(self):
        """Lazy load the semaphore to ensure it's created inside the active asyncio event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(3)
        return self._semaphore
        
    async def get_instruments(self):
        """Fetches and caches the instrument master list once per day."""
        cached = cache.get("instrument_list")
        if cached is not None:
            return cached
            
        async with self.semaphore:
            instruments = await asyncio.to_thread(self.kite.instruments)
            df = pd.DataFrame(instruments)
            cache.set("instrument_list", df)
            return df

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    async def get_historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> pd.DataFrame:
        """Fetches historical data, wrapping Kite's sync API in an async call."""
        async with self.semaphore:
            records = await asyncio.to_thread(
                self.kite.historical_data, 
                instrument_token, 
                from_date, 
                to_date, 
                interval
            )
            df = pd.DataFrame(records)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            return df
            
    @retry(wait=wait_exponential(multiplier=1, min=1, max=5), stop=stop_after_attempt(3))
    async def get_quote(self, instruments: list[str]) -> dict:
        """Fetch real-time snapshot/LTP for a list of instruments (e.g. 'NSE:NIFTY 50')."""
        async with self.semaphore:
            quotes = await asyncio.to_thread(self.kite.quote, instruments)
            
            # Data Freshness Validation via strict timezone normalization
            fresh_quotes = {}
            now_ist_naive = TimezoneNormalizer.now_ist_naive()
            for inst, data in quotes.items():
                if 'timestamp' in data:
                    diff = (now_ist_naive - data['timestamp']).total_seconds()
                    
                    # Divergent Sensitivity Execution Locks
                    # 1. Spot Tracker (NSE): The signal source of truth. Ultra-strict < 3s latency.
                    # 2. Option Hedge (NFO): Subject to Bid-Ask and slippage physical gaps. Relaxed < 300s.
                    if inst.startswith("NSE:"):
                        is_fresh = (0 <= diff <= 3)
                    elif inst.startswith("NFO:"):
                        is_fresh = (0 <= diff <= 300)
                    else:
                        is_fresh = (0 <= diff <= 10) # Fallback
                        
                    if is_fresh:
                        fresh_quotes[inst] = data
                    else:
                        logger.warning(f"Stale quote received for {inst}. Delay: {diff}s")
                else:
                    fresh_quotes[inst] = data
            return fresh_quotes

    async def get_ltp(self, instruments: list[str]) -> dict:
        """Fetch only LTP for a list of instruments."""
        async with self.semaphore:
            return await asyncio.to_thread(self.kite.ltp, instruments)
            
    async def get_margins(self, params: list[dict]) -> list[dict]:
        """Fetch official margin requirements for a list of trades."""
        async with self.semaphore:
            return await asyncio.to_thread(self.kite.basket_order_margins, params, consider_positions=False)

# Global broker instance
broker = BrokerFetcher()
