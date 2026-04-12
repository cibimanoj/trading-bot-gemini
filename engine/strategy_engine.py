import pandas as pd
from typing import Dict, Any

from engine.regime import RegimeType

from datetime import datetime
import pytz

class StrategyEngine:
    @staticmethod
    def select_strategy(regime: RegimeType, bias: str, iv_percentile: float) -> str:
        """
        Determines the strategy to deploy based on the regime, bias, and time of day.
        """
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist).time()
        start_time = datetime.strptime("09:30:00", "%H:%M:%S").time()
        end_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
        
        if now < start_time or now > end_time:
            return "NO_TRADE"  # Outside safe trading hours
        if regime == RegimeType.RANGE:
            if iv_percentile > 60:
                if bias == "NEUTRAL":
                    return "IRON_CONDOR"
                elif bias == "BULLISH":
                    return "BULL_PUT_SPREAD"
                elif bias == "BEARISH":
                    return "BEAR_CALL_SPREAD"
            else:
                return "NO_TRADE"  # Range but low IV -> bad premium
                
        elif regime in [RegimeType.TREND_STRONG, RegimeType.TREND_MILD]:
            if bias == "BULLISH":
                return "BUY_CE"
            elif bias == "BEARISH":
                return "BUY_PE"
                
        return "NO_TRADE"

    @staticmethod
    def select_strikes(strategy: str, option_chain: pd.DataFrame, current_spot: float, index_name: str) -> Dict[str, Any]:
        """
        Selects specific strikes using Delta.
        For Selling: Delta ~ 0.15 to 0.20
        Hedge legs are chosen mechanically: 3 strikes away for Nifty, 4 strikes for BankNifty
        """
        result = {}
        option_chain = option_chain.copy()
        # Ensure delta is positive for easier comparison
        option_chain['abs_delta'] = option_chain['Delta'].abs()
        
        calls = option_chain[option_chain['type'] == 'c'].copy().sort_values('strike')
        puts = option_chain[option_chain['type'] == 'p'].copy().sort_values('strike')

        # Determine Strike Step & Hedge Width
        strike_step = 50 if index_name == "NIFTY" else 100
        hedge_width = 3 if index_name == "NIFTY" else 4
        point_width = strike_step * hedge_width

        if strategy == "IRON_CONDOR":
            sell_ce = calls.iloc[(calls['abs_delta'] - 0.15).abs().argsort()[:1]]
            sell_pe = puts.iloc[(puts['abs_delta'] - 0.15).abs().argsort()[:1]]
            
            if not sell_ce.empty and not sell_pe.empty:
                sell_ce_strike = sell_ce.iloc[0]['strike']
                buy_ce_strike = sell_ce_strike + point_width
                buy_ce = calls[calls['strike'] >= buy_ce_strike].head(1) # Bound filter
                
                sell_pe_strike = sell_pe.iloc[0]['strike']
                buy_pe_strike = sell_pe_strike - point_width
                buy_pe = puts[puts['strike'] <= buy_pe_strike].sort_values('strike', ascending=False).head(1)
                
                if not buy_ce.empty and not buy_pe.empty:
                    result = {
                        'sell_ce': sell_ce.iloc[0].to_dict(),
                        'buy_ce': buy_ce.iloc[0].to_dict(),
                        'sell_pe': sell_pe.iloc[0].to_dict(),
                        'buy_pe': buy_pe.iloc[0].to_dict()
                    }

        elif strategy == "BULL_PUT_SPREAD":
            sell_pe = puts.iloc[(puts['abs_delta'] - 0.20).abs().argsort()[:1]]
            if not sell_pe.empty:
                sell_pe_strike = sell_pe.iloc[0]['strike']
                buy_pe_strike = sell_pe_strike - point_width
                buy_pe = puts[puts['strike'] <= buy_pe_strike].sort_values('strike', ascending=False).head(1)
                
                if not buy_pe.empty:
                    result = {
                        'sell_pe': sell_pe.iloc[0].to_dict(),
                        'buy_pe': buy_pe.iloc[0].to_dict()
                    }
                
        elif strategy == "BEAR_CALL_SPREAD":
            sell_ce = calls.iloc[(calls['abs_delta'] - 0.20).abs().argsort()[:1]]
            if not sell_ce.empty:
                sell_ce_strike = sell_ce.iloc[0]['strike']
                buy_ce_strike = sell_ce_strike + point_width
                buy_ce = calls[calls['strike'] >= buy_ce_strike].head(1)
                
                if not buy_ce.empty:
                    result = {
                        'sell_ce': sell_ce.iloc[0].to_dict(),
                        'buy_ce': buy_ce.iloc[0].to_dict()
                    }

        elif strategy in ["BUY_CE", "BUY_PE"]:
            target_delta = 0.50
            if strategy == "BUY_CE":
                target = calls.iloc[(calls['abs_delta'] - target_delta).abs().argsort()[:1]]
                if not target.empty:
                    result = {'buy_ce': target.iloc[0].to_dict()}
            else:
                target = puts.iloc[(puts['abs_delta'] - target_delta).abs().argsort()[:1]]
                if not target.empty:
                    result = {'buy_pe': target.iloc[0].to_dict()}

        return result
