from config import settings
from data.broker_fetcher import broker

class CapitalManager:
    @staticmethod
    async def calculate_margin_and_lots(strategy: str, legs: dict, current_capital: float) -> tuple[float, int, float]:
        """
        Implements Two-Step Validation:
        1. Approximate required margin for the strategy.
        2. Validate tightly against Kite official margin API.
        
        Returns: (Total Used Margin, Number of Lots, Margin Per Lot)
        """
        usable_capital = current_capital * settings.MAX_CAPITAL_USE
        
        # Prepare params for Kite Margin API
        margin_params = []
        for leg_type, leg_data in legs.items():
            trade_type = 'SELL' if 'sell' in leg_type else 'BUY'
            
            # Using 1 lot to find the exact margin required per single unit
            # For BankNifty it might be 15, Nifty 50, but we assume we know the lot size from leg_data
            lot_size = leg_data.get('lot_size', 50) 
            
            margin_params.append({
                "exchange": "NFO",
                "tradingsymbol": leg_data.get('tradingsymbol'),
                "transaction_type": trade_type,
                "variety": "regular",
                "product": "NRML",
                "order_type": "MARKET",
                "quantity": lot_size
            })

        # Official Kite Margin check (Two-Step Validation Source of Truth)
        try:
            margins = await broker.get_margins(margin_params)
            if 'initial_margin' in margins and 'total' in margins['initial_margin']:
                total_margin_per_lot_setup = margins['initial_margin']['total']
            else:
                total_margin_per_lot_setup = CapitalManager.approximate_margin(strategy, legs)
        except Exception:
            total_margin_per_lot_setup = CapitalManager.approximate_margin(strategy, legs)

        # Calculate maximum potential structural loss per lot
        lot_size = list(legs.values())[0].get('lot_size', 50) if legs else 50
        max_loss_per_lot = 0
        
        if strategy == "IRON_CONDOR":
            width_ce = abs(legs['sell_ce']['strike'] - legs['buy_ce']['strike'])
            width_pe = abs(legs['sell_pe']['strike'] - legs['buy_pe']['strike'])
            net_credit = (legs['sell_ce'].get('premium',0) + legs['sell_pe'].get('premium',0)) - (legs['buy_ce'].get('premium',0) + legs['buy_pe'].get('premium',0))
            max_loss_per_lot = (max(width_ce, width_pe) - net_credit) * lot_size
        elif strategy in ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"]:
            s_leg = legs.get('sell_ce') or legs.get('sell_pe')
            b_leg = legs.get('buy_ce') or legs.get('buy_pe')
            width = abs(s_leg['strike'] - b_leg['strike'])
            net_credit = s_leg.get('premium',0) - b_leg.get('premium',0)
            max_loss_per_lot = (width - net_credit) * lot_size
        elif strategy in ["BUY_CE", "BUY_PE"]:
            b_leg = legs.get('buy_ce') or legs.get('buy_pe')
            max_loss_per_lot = b_leg.get('premium',0) * lot_size
            
        max_acceptable_loss = current_capital * settings.MAX_LOSS_CAPITAL_PCT
        lots_by_loss = int(max_acceptable_loss // max_loss_per_lot) if max_loss_per_lot > 0 else float('inf')

        # Calculate lots allowed by margin
        if total_margin_per_lot_setup > 0:
            lots = int(usable_capital // total_margin_per_lot_setup)
        else:
            lots = 0
            
        lots = min(lots, lots_by_loss)

        # Apply State Machine Lot Reduction or Halt
        from engine.risk_manager import risk_manager
        lots = risk_manager.adjust_lot_size(lots)

        total_margin_used = lots * total_margin_per_lot_setup
        return total_margin_used, lots, total_margin_per_lot_setup

    @staticmethod
    def approximate_margin(strategy: str, legs: dict) -> float:
        """Approximation based on spread width."""
        lot_size = list(legs.values())[0].get('lot_size', 50) if legs else 50
        
        if strategy == "IRON_CONDOR":
            width_ce = abs(legs['sell_ce']['strike'] - legs['buy_ce']['strike'])
            width_pe = abs(legs['sell_pe']['strike'] - legs['buy_pe']['strike'])
            max_width = max(width_ce, width_pe)
            return max_width * lot_size
        elif strategy in ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"]:
            s_leg = legs.get('sell_ce') or legs.get('sell_pe')
            b_leg = legs.get('buy_ce') or legs.get('buy_pe')
            width = abs(s_leg['strike'] - b_leg['strike'])
            return width * lot_size
        elif strategy in ["BUY_CE", "BUY_PE"]:
            b_leg = legs.get('buy_ce') or legs.get('buy_pe')
            return b_leg['premium'] * lot_size
        return 0
