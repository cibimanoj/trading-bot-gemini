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
            
        def _fetch_and_parse():
            instruments = self.kite.instruments(exchange="NFO") + self.kite.instruments(exchange="NSE")
            return pd.DataFrame(instruments)

        async with self.semaphore:
            df = await asyncio.to_thread(_fetch_and_parse)
            cache.set("instrument_list", df)
            return df

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    async def get_historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> pd.DataFrame:
        """Fetches historical data, wrapping Kite's sync API in an async call."""
        def _fetch_hist():
            records = self.kite.historical_data(
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

        async with self.semaphore:
            return await asyncio.to_thread(_fetch_hist)
            
    @retry(wait=wait_exponential(multiplier=1, min=1, max=5), stop=stop_after_attempt(3))
    async def get_quote(self, instruments: list[str]) -> dict:
        """Fetch real-time snapshot/LTP for a list of instruments (e.g. 'NSE:NIFTY 50')."""
        async with self.semaphore:
            quotes = await asyncio.to_thread(self.kite.quote, instruments)
            
            # Data Freshness Validation via strict timezone normalization
            fresh_quotes = {}
            now_ist_naive = TimezoneNormalizer.now_ist_naive()
            spot_max = settings.QUOTE_STALE_SPOT_SEC
            nfo_max = settings.QUOTE_STALE_NFO_SEC
            for inst, data in quotes.items():
                if 'timestamp' in data:
                    diff = (now_ist_naive - data['timestamp']).total_seconds()
                    # Small negative slack for clock skew vs exchange timestamp
                    if inst.startswith("NSE:"):
                        is_fresh = (-5.0 <= diff <= spot_max)
                    elif inst.startswith("NFO:"):
                        is_fresh = (-5.0 <= diff <= nfo_max)
                    else:
                        is_fresh = (-5.0 <= diff <= 10.0)
                        
                    if is_fresh:
                        fresh_quotes[inst] = data
                    else:
                        logger.warning(f"Stale quote received for {inst}. Delay: {diff}s")
                else:
                    if inst.startswith("NSE:"):
                        logger.warning(f"No timestamp for {inst}; quote excluded for freshness.")
                    else:
                        fresh_quotes[inst] = data
            return fresh_quotes

    async def get_ltp(self, instruments: list[str]) -> dict:
        """Fetch only LTP for a list of instruments."""
        async with self.semaphore:
            return await asyncio.to_thread(self.kite.ltp, instruments)
            
    async def get_margins(self, params: list[dict]) -> dict:
        """Fetch basket margin dict (initial/final/orders) from Kite."""
        async with self.semaphore:
            return await asyncio.to_thread(self.kite.basket_order_margins, params, consider_positions=False)

# Global broker instance
broker = BrokerFetcher()
