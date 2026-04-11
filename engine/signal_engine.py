import datetime
from engine.capital_manager import CapitalManager

class SignalEngine:
    @staticmethod
    def generate_signal(strategy: str, legs: dict, index_name: str, regime: str, confidence: int, current_spot: float, used_capital: float, lots: int, current_capital: float = 0.0) -> dict:
        """
        Generates the final comprehensive trade signal detailing strikes, SL, Targets.
        """
        # Assign risk rules
        for leg_type, leg_data in legs.items():
            premium = leg_data.get('premium', 0)
            
            if 'sell' in leg_type:
                # Sell SL: 30-40% above premium
                leg_data['sl'] = round(premium * 1.35, 2)
                # Sell Target: 50-60% decay
                leg_data['target'] = round(premium * 0.45, 2)
            else:
                # Buy SL: 30% below premium
                leg_data['sl'] = round(premium * 0.70, 2)
                # Buy Target: 50% increase
                leg_data['target'] = round(premium * 1.50, 2)

        # Spot based SL
        spot_sl = ""
        target_decay_msg = ""
        if strategy == "IRON_CONDOR":
            sell_ce_strike = legs['sell_ce']['strike']
            sell_pe_strike = legs['sell_pe']['strike']
            spot_sl = f"Spot > {sell_ce_strike + 50} / < {sell_pe_strike - 50}"
            target_decay_msg = "50-60% premium decay"
        elif strategy == "BULL_PUT_SPREAD":
            sell_pe_strike = legs['sell_pe']['strike']
            spot_sl = f"Spot < {sell_pe_strike - 25}"
            target_decay_msg = "50-60% premium decay"
        elif strategy == "BEAR_CALL_SPREAD":
            sell_ce_strike = legs['sell_ce']['strike']
            spot_sl = f"Spot > {sell_ce_strike + 25}"
            target_decay_msg = "50-60% premium decay"
        elif "BUY" in strategy:
            spot_sl = f"Spot breaches closest SR level"
            target_decay_msg = "Hold for trend extension or trailing SL"

        return {
            'index': index_name,
            'regime': regime,
            'strategy': strategy,
            'confidence': confidence,
            'legs': legs,
            'spot': current_spot,
            'capital_used': used_capital,
            'lots': lots,
            'current_capital': current_capital,
            'spot_sl': spot_sl,
            'target_msg': target_decay_msg,
            'exit_time': datetime.time(15, 10).strftime("%I:%M %p") + " (Strict Time Exit)"
        }
