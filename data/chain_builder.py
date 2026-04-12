import asyncio
import pandas as pd
from datetime import datetime, date
import pytz
from config import settings
from data.broker_fetcher import broker
from data.validator import validate_dataframe

class ChainBuilder:
    @staticmethod
    async def build_option_chain(index_symbol: str, spot_price: float, num_strikes: int = 15) -> pd.DataFrame:
        """
        Builds the option chain for the nearest expiry.
        :param index_symbol: e.g. "NIFTY" or "BANKNIFTY"
        """
        df_instruments = await broker.get_instruments()
        
        def _filter_instruments(df_instruments):
            options = df_instruments[(df_instruments['name'] == index_symbol) & 
                                     (df_instruments['segment'] == 'NFO-OPT')].copy()
            if options.empty: return options, None
            
            options['expiry'] = pd.to_datetime(options['expiry']).dt.date
            today = date.today()
            future_expiries = options[options['expiry'] >= today]['expiry'].unique()
            if len(future_expiries) == 0: return pd.DataFrame(), None
            
            future_expiries.sort()
            nearest_expiry = future_expiries[0]
            chain = options[options['expiry'] == nearest_expiry].copy()
            
            strike_step = 50 if index_symbol == "NIFTY" else 100
            lower_bound = spot_price - (num_strikes * strike_step)
            upper_bound = spot_price + (num_strikes * strike_step)
            chain = chain[(chain['strike'] >= lower_bound) & (chain['strike'] <= upper_bound)]
            default_lot = settings.NIFTY_LOT_SIZE if index_symbol == "NIFTY" else settings.BANKNIFTY_LOT_SIZE
            if "lot_size" not in chain.columns:
                chain["lot_size"] = default_lot
            else:
                chain["lot_size"] = pd.to_numeric(chain["lot_size"], errors="coerce").fillna(default_lot).astype(int)
            return chain, nearest_expiry
            
        chain, nearest_expiry = await asyncio.to_thread(_filter_instruments, df_instruments)
        
        if chain is None or chain.empty:
            return pd.DataFrame()
        
        # Fetch LTPs and OI
        instrument_keys = [f"NFO:{ts}" for ts in chain['tradingsymbol']]
        if not instrument_keys:
            return pd.DataFrame()
            
        quotes = await broker.get_quote(instrument_keys)
        
        def _process_merging(chain_df, quotes_data, expiry_d):
            ltps, ois, bid_ask_spreads = [], [], []
            for ts in chain_df['tradingsymbol']:
                key = f"NFO:{ts}"
                if key in quotes_data:
                    data = quotes_data[key]
                    ltps.append(data.get('last_price', 0))
                    ois.append(data.get('oi', 0))
                    
                    depth = data.get('depth', {})
                    buy_depth = depth.get('buy', [])
                    sell_depth = depth.get('sell', [])
                    bid = buy_depth[0]['price'] if buy_depth else data.get('last_price', 0)
                    ask = sell_depth[0]['price'] if sell_depth else data.get('last_price', 0)
                    
                    if ask > 0 and bid > 0 and ask != bid:
                        spread_pct = (ask - bid) / ask
                        bid_ask_spreads.append(spread_pct)
                    else:
                        bid_ask_spreads.append(1.0) # toxic/illiquid fallback
                else:
                    ltps.append(0)
                    ois.append(0)
                    bid_ask_spreads.append(1.0) # 100% spread (toxic, will be dropped)
            
            chain_df['premium'] = ltps
            chain_df['oi'] = ois
            chain_df['type'] = chain_df['instrument_type'].map({'CE': 'c', 'PE': 'p'})
            chain_df['spread_pct'] = bid_ask_spreads
            
            # Liquidity Filters: Drop low OI and drop inherently wide Bid-Ask spreads (> 5%)
            chain_df = chain_df[(chain_df['oi'] > 1000) & (chain_df['spread_pct'] <= 0.05)]
            
            if chain_df.empty: return chain_df

            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
            expiry_dt = ist.localize(datetime.combine(expiry_d, datetime.strptime("15:30:00", "%H:%M:%S").time()))
            seconds_to_expiry = (expiry_dt - now).total_seconds()
            if seconds_to_expiry <= 0: seconds_to_expiry = 3600
                
            chain_df['time_to_expiry_years'] = seconds_to_expiry / (365 * 24 * 60 * 60)
            return chain_df
            
        chain = await asyncio.to_thread(_process_merging, chain, quotes, nearest_expiry)
        if not validate_dataframe(chain, ["strike", "tradingsymbol", "premium", "type"]):
            return pd.DataFrame()
        return chain
