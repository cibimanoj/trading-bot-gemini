import logging
import math
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from config import settings
from data.broker_fetcher import broker
from data.cache import cache
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
from utils.timezone import TimezoneNormalizer

logger = logging.getLogger(__name__)

def _safe_float(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


async def _resolve_instrument_token(exchange: str, tradingsymbol_candidates: List[str]) -> Optional[int]:
    """
    Resolve instrument_token via the daily instrument master (cached inside broker.get_instruments()).
    Avoids hardcoding tokens (which can change).
    """
    day_key = f"resolved_token:{exchange}:{'|'.join(tradingsymbol_candidates)}"
    cached_token = cache.get(day_key)
    if cached_token is not None:
        return cached_token

    df = await broker.get_instruments()
    if df is None or getattr(df, "empty", True):
        return None

    required = {"exchange", "tradingsymbol", "instrument_token"}
    if not required.issubset(set(df.columns)):
        return None

    subset = df[df["exchange"] == exchange].copy()
    if subset.empty:
        return None

    for ts in tradingsymbol_candidates:
        row = subset[subset["tradingsymbol"] == ts]
        if not row.empty:
            try:
                token = int(row.iloc[0]["instrument_token"])
                if token > 0:
                    cache.set(day_key, token, ttl_seconds=86400 * 4)
                    return token
            except Exception:
                continue

    return None

class AnalyzerOrchestrator:
    @staticmethod
    async def analyze_market(index_name: str) -> Optional[Dict[str, Any]]:
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
        try:
            spot_price = float(quotes[symbol].get("last_price"))
        except Exception:
            logger.error("Spot quote missing/invalid last_price for %s. Quote=%s", symbol, quotes.get(symbol))
            return None
        
        # 2. Build Option Chain
        chain_df = await ChainBuilder.build_option_chain(index_name, spot_price)
        if chain_df.empty:
            logger.error("Option chain is empty.")
            return None

        # 3. Fetch Historical Data for ADX (Using 15-minute data, last 5 days)
        if index_name == "NIFTY":
            token = await _resolve_instrument_token("NSE", ["NIFTY 50"])
        elif index_name == "BANKNIFTY":
            token = await _resolve_instrument_token("NSE", ["NIFTY BANK"])
        else:
            logger.error("Unsupported index_name %r.", index_name)
            return None

        if token is None:
            logger.error("Could not resolve instrument token for %s via instrument master.", index_name)
            return None

        # Use naive IST windows for Kite historical APIs (Kite timestamps are naive IST-like).
        to_date = TimezoneNormalizer.now_ist_naive()
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

        adx_val = _safe_float(adx_val)
        dmp_val = _safe_float(dmp_val)
        dmn_val = _safe_float(dmn_val)

        # 4. Fetch India VIX history for IV Percentile
        # Wait, if we can't fetch VIX easily, let's use the local IV from chain
        
        # 5. Calculate Greeks and local IV for strike selection
        # Sanitize before greeks: remove non-positive premiums/strikes and obviously broken rows.
        chain_df = chain_df.copy()
        if not validate_dataframe(chain_df, ["strike", "premium", "time_to_expiry_years", "type"]):
            logger.error("Option chain missing required columns for Greeks/IV.")
            return None
        chain_df["premium"] = pd.to_numeric(chain_df["premium"], errors="coerce")
        chain_df["strike"] = pd.to_numeric(chain_df["strike"], errors="coerce")
        chain_df["time_to_expiry_years"] = pd.to_numeric(chain_df["time_to_expiry_years"], errors="coerce")
        chain_df = chain_df[
            chain_df["premium"].notna()
            & chain_df["strike"].notna()
            & chain_df["time_to_expiry_years"].notna()
            & (chain_df["premium"] > 0)
            & (chain_df["strike"] > 0)
            & (chain_df["time_to_expiry_years"] > 0)
        ]
        if chain_df.empty:
            logger.error("Option chain has no valid premiums for IV/Greeks.")
            return None

        try:
            tte = float(chain_df["time_to_expiry_years"].iloc[0])
            if not math.isfinite(tte) or tte <= 0:
                raise ValueError("time_to_expiry_years invalid")
            greeks = await asyncio.to_thread(
                Indicators.calculate_greeks_and_iv,
                spot_price,
                chain_df['strike'].values,
                chain_df['premium'].values,
                tte,
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

        # Drop rows where IV/Delta are not finite (py_vollib can output NaNs for bad quotes)
        chain_df["IV"] = pd.to_numeric(chain_df["IV"], errors="coerce")
        chain_df["Delta"] = pd.to_numeric(chain_df["Delta"], errors="coerce")
        chain_df = chain_df[chain_df["IV"].notna() & chain_df["Delta"].notna()]
        if chain_df.empty:
            logger.error("Option chain IV/Delta all invalid after sanitization.")
            return None

        # 6. Calc PCR and average chain IV
        pcr = Indicators.calculate_pcr(chain_df)
        avg_iv = _safe_float(chain_df["IV"].mean(), default=0.0)

        # 7. Rolling PCR z-score from DB history (current tick appended before insert)
        lookback = settings.MARKET_SNAPSHOT_LOOKBACK
        prior_pcr = await db_instance.get_recent_pcr_values(index_name, lookback - 1)
        pcr_series = pd.Series(prior_pcr + [pcr])
        pcr_zscore = Indicators.calculate_pcr_zscore(pcr_series)
        if len(prior_pcr) < 5:
            pcr_zscore = 0.0
        elif math.isnan(pcr_zscore):
            pcr_zscore = 0.0

        # IV rank should be based on option IV history (chain avg IV). Keep VIX percentile separate.
        prior_iv = await db_instance.get_recent_avg_iv_values(index_name, lookback - 1)
        if len(prior_iv) >= 5:
            iv_series = pd.Series(prior_iv + [avg_iv])
            chain_iv_percentile = Indicators.iv_percentile(iv_series)
        else:
            chain_iv_percentile = 75.0 if avg_iv > 0.20 else 40.0

        # Optional: VIX percentile (proxy only). Do not feed into strategy thresholds that expect IV rank.
        vix_percentile: Optional[float] = None
        vix_token = await _resolve_instrument_token("NSE", ["INDIA VIX"])
        if vix_token is not None:
            vix_to = TimezoneNormalizer.now_ist_naive()
            vix_from = vix_to - timedelta(days=30)
            vix_df = await broker.get_historical_data(vix_token, vix_from, vix_to, "day")
            if not vix_df.empty and len(vix_df) > 5 and "close" in vix_df.columns:
                vix_percentile = Indicators.iv_percentile(vix_df["close"])

        await db_instance.insert_market_snapshot(index_name, pcr, avg_iv, chain_iv_percentile)

        # 8. Determine Regime and Bias
        regime = MarketRegime.determine_regime(adx_val, chain_iv_percentile, pcr)
        bias = MarketRegime.determine_directional_bias(dmp_val, dmn_val, pcr)

        # 9. Score Setup
        score = Scorer.score_setup(regime, bias, chain_iv_percentile, pcr_zscore)
        
        logger.info(f"Analysis complete: Regime={regime.name}, Bias={bias}, Score={score}")

        if score < settings.MIN_CONFIDENCE_SCORE:
            logger.info("Score below minimum confidence. No signal.")
            return None

        # 10. Select Strategy & Strikes
        strategy = StrategyEngine.select_strategy(regime, bias, chain_iv_percentile)
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
        def _legs_signature(sig: Dict[str, Any]) -> str:
            try:
                details = sig.get("trade_details") or {}
                legs_list = details.get("legs") or []
                syms = sorted(
                    [str(x.get("symbol", "")).strip() for x in legs_list if isinstance(x, dict)]
                )
                syms = [s for s in syms if s]
                return f"{sig.get('index_name')}|{sig.get('strategy_type')}|{','.join(syms)}"
            except Exception:
                return f"{sig.get('index_name')}|{sig.get('strategy_type')}|"

        current_sig_key = f"{index_name}|{strategy}|{','.join(sorted([str(v.get('tradingsymbol','')).strip() for v in legs.values() if isinstance(v, dict)])))}"

        for past_signal in recent_signals:
            if _legs_signature(past_signal) == current_sig_key:
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
            def _to_float_or_none(v):
                try:
                    if v is None:
                        return None
                    f = float(v)
                    if math.isnan(f) or math.isinf(f):
                        return None
                    return f
                except Exception:
                    return None

            delta_val = _to_float_or_none((leg_data or {}).get("Delta"))
            iv_val = _to_float_or_none((leg_data or {}).get("IV"))
            
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
            "chain_iv_percentile": float(chain_iv_percentile),
            "vix_percentile": float(vix_percentile) if vix_percentile is not None else None,
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
