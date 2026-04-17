import logging
import math
import asyncio
import pandas as pd
from datetime import datetime, timedelta

from config import settings
from data.broker_fetcher import broker
from data.chain_builder import ChainBuilder
from data.validator import validate_dataframe
from engine.indicators import Indicators
from engine.regime import MarketRegime
from engine.scoring import Scorer
from engine.strategy_engine import StrategyEngine
from engine.capital_manager import CapitalManager
from engine.signal_engine import SignalEngine
from engine.portfolio_tracker import PortfolioTracker
from engine.risk_manager import risk_manager, TradeMode
from db.database import db_instance

logger = logging.getLogger(__name__)

# Map indices to their Kite instrument tokens for historical data (must match Kite instrument master)
INDEX_TOKENS = {
    "NIFTY": 256265,
    "BANKNIFTY": 260105
}
VIX_TOKEN = 264969

class AnalyzerOrchestrator:
    @staticmethod
    async def analyze_market(index_name: str) -> dict | None:
        """
        Full orchestration of market analysis.
        """
        if risk_manager.mode == TradeMode.HALTED:
            logger.info("Skipping analysis: risk mode HALTED.")
            return None

        logger.info(f"Starting analysis for {index_name}")
        
        # 1. Fetch spot price
        symbol = f"NSE:{index_name} 50" if index_name == "NIFTY" else f"NSE:NIFTY BANK"
        quotes = await broker.get_quote([symbol])
        if symbol not in quotes:
            logger.error("Failed to fetch spot quote.")
            return None
        spot_price = quotes[symbol]['last_price']
        
        # 2. Build Option Chain
        chain_df = await ChainBuilder.build_option_chain(index_name, spot_price)
        if chain_df.empty:
            logger.error("Option chain is empty.")
            return None

        # 3. Fetch Historical Data for ADX (Using 15-minute data, last 5 days)
        if index_name not in INDEX_TOKENS:
            logger.error("Unsupported index_name %r — add token to INDEX_TOKENS.", index_name)
            return None
        token = INDEX_TOKENS[index_name]
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        hist_df = await broker.get_historical_data(token, from_date, to_date, "15minute")
        
        if hist_df.empty or len(hist_df) < 15:
            logger.error("Not enough historical data for indicators.")
            return None
        if not validate_dataframe(hist_df, ["high", "low", "close"]):
            logger.error("Historical data missing required OHLC columns.")
            return None
            
        hist_df = Indicators.calculate_adx(hist_df, window=14)
        latest_row = hist_df.iloc[-1]
        adx_val = latest_row.get('ADX', 0)
        dmp_val = latest_row.get('DMP', 0)
        dmn_val = latest_row.get('DMN', 0)

        def _finite_scalar(x, default=0.0) -> float:
            try:
                v = float(x)
                if math.isnan(v) or math.isinf(v):
                    return default
                return v
            except (TypeError, ValueError):
                return default

        adx_val = _finite_scalar(adx_val)
        dmp_val = _finite_scalar(dmp_val)
        dmn_val = _finite_scalar(dmn_val)

        # 4. Fetch India VIX history for IV Percentile
        # Wait, if we can't fetch VIX easily, let's use the local IV from chain
        
        # 5. Calculate Greeks and local IV for strike selection
        try:
            greeks = await asyncio.to_thread(
                Indicators.calculate_greeks_and_iv,
                spot_price,
                chain_df['strike'].values,
                chain_df['premium'].values,
                chain_df['time_to_expiry_years'].iloc[0],
                chain_df['type'].values
            )
            chain_df['IV'] = greeks['IV']
            chain_df['Delta'] = greeks['Delta']
        except Exception as e:
            logger.error(f"Failed to calculate Greeks: {e}")
            return None

        if not validate_dataframe(chain_df, ["IV", "Delta", "strike", "premium"]):
            logger.error("Option chain missing IV/Delta or core columns after Greeks.")
            return None

        # 6. Calc PCR and average chain IV
        pcr = Indicators.calculate_pcr(chain_df)
        avg_iv = float(chain_df["IV"].mean())
        if math.isnan(avg_iv):
            avg_iv = 0.0

        # 7. Rolling PCR z-score from DB history (current tick appended before insert)
        lookback = settings.MARKET_SNAPSHOT_LOOKBACK
        prior_pcr = await db_instance.get_recent_pcr_values(index_name, lookback - 1)
        pcr_series = pd.Series(prior_pcr + [pcr])
        pcr_zscore = Indicators.calculate_pcr_zscore(pcr_series)
        if len(prior_pcr) < 5:
            pcr_zscore = 0.0
        elif math.isnan(pcr_zscore):
            pcr_zscore = 0.0

        # IV percentile proxy: VIX close percentile when daily VIX loads; else rolling rank of chain avg_iv (different scales — both feed regime/scoring consistently per branch)
        vix_df = await broker.get_historical_data(
            VIX_TOKEN, datetime.now() - timedelta(days=30), datetime.now(), "day"
        )
        if not vix_df.empty and len(vix_df) > 5:
            iv_percentile = Indicators.iv_percentile(vix_df["close"])
        else:
            prior_iv = await db_instance.get_recent_avg_iv_values(index_name, lookback - 1)
            if len(prior_iv) >= 5:
                iv_series = pd.Series(prior_iv + [avg_iv])
                iv_percentile = Indicators.iv_percentile(iv_series)
            else:
                iv_percentile = 75.0 if avg_iv > 0.20 else 40.0

        await db_instance.insert_market_snapshot(index_name, pcr, avg_iv, iv_percentile)

        # 8. Determine Regime and Bias
        regime = MarketRegime.determine_regime(adx_val, iv_percentile, pcr)
        bias = MarketRegime.determine_directional_bias(dmp_val, dmn_val, pcr)

        # 9. Score Setup
        score = Scorer.score_setup(regime, bias, iv_percentile, pcr_zscore)
        
        logger.info(f"Analysis complete: Regime={regime.name}, Bias={bias}, Score={score}")

        if score < settings.MIN_CONFIDENCE_SCORE:
            logger.info("Score below minimum confidence. No signal.")
            return None

        # 10. Select Strategy & Strikes
        strategy = StrategyEngine.select_strategy(regime, bias, iv_percentile)
        if strategy == "NO_TRADE":
            return None
            
        legs = StrategyEngine.select_strikes(strategy, chain_df, spot_price, index_name)
        if not legs:
            logger.info("Could not find suitable strikes matching criteria.")
            return None

        # 11. Capital Management and Margin
        current_capital = await PortfolioTracker.get_current_capital()
        margin_used, lots, margin_per_lot = await CapitalManager.calculate_margin_and_lots(
            strategy, legs, current_capital, index_name
        )
        
        if lots == 0:
            logger.warning("Insufficient capital to allocate even 1 lot.")
            return None

        # 12. Ghost Filter (Temporal Debouncing to prevent spamming identical executions)
        recent_signals = await db_instance.get_recent_signals(limit=25)
        for past_signal in recent_signals:
            if past_signal['strategy_type'] == strategy and past_signal['index_name'] == index_name:
                ts_obj = past_signal['timestamp']
                try:
                    from datetime import timezone
                    from utils.sqlite_time import parse_sqlite_utc_timestamp

                    past_time = parse_sqlite_utc_timestamp(ts_obj)
                    if past_time is None:
                        continue
                    current_utc = datetime.now(timezone.utc)
                    if (current_utc - past_time).total_seconds() < 900: # 15 min debounce block
                        logger.info(f"Signal {strategy} dropped by Ghost Debounce Filter (Identical trade < 15m ago).")
                        return None
                except Exception as e:
                    logger.warning(f"Deduplication skip failed parsing timestamp: {e}")

        # 12. Generate Signal
        signal = SignalEngine.generate_signal(
            strategy=strategy,
            legs=legs,
            index_name=index_name,
            regime=regime.name,
            confidence=score,
            current_spot=spot_price,
            used_capital=margin_used,
            lots=lots,
            current_capital=current_capital
        )

        # 13. Format JSON structure for backtest database
        formatted_legs = []
        for leg_type, leg_data in signal['legs'].items():
            action = "SELL" if "sell" in leg_type else "BUY"
            
            # Sanitization of py_vollib's NaN outputs to strictly conform to SQLite JSON schema
            delta_val = float(leg_data.get('Delta', 0.0))
            if math.isnan(delta_val): delta_val = None
            iv_val = float(leg_data.get('IV', 0.0))
            if math.isnan(iv_val): iv_val = None
            
            formatted_legs.append({
                "action": action,
                "symbol": leg_data.get('tradingsymbol', ''),
                "price": leg_data.get('premium', 0.0),
                "delta": delta_val,
                "iv": iv_val
            })
            
        json_details = {
            "strategy": strategy,
            "regime": regime.name,
            "pcr_z": float(pcr_zscore),
            "legs": formatted_legs,
            "total_margin_utilized": margin_used,
            "slippage_estimate": 0.50
        }

        # 14. Save to DB
        await db_instance.save_signal(
            index_name=index_name,
            regime=regime.name,
            strategy=strategy,
            details=json_details,
            capital_used=margin_used,
            confidence=score
        )

        return signal
