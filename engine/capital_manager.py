import math
import logging
from typing import Any

from config import settings
from data.broker_fetcher import broker

logger = logging.getLogger(__name__)

class CapitalManager:
    @staticmethod
    def _lot_size_for_leg(leg_data: dict, index_name: str) -> int:
        raw = leg_data.get("lot_size")
        if raw is not None:
            try:
                n = int(float(raw))
                if n > 0:
                    return n
            except (TypeError, ValueError):
                pass
        if index_name == "BANKNIFTY":
            return settings.BANKNIFTY_LOT_SIZE
        return settings.NIFTY_LOT_SIZE

    @staticmethod
    def _total_from_kite_basket_response(margins: Any) -> float | None:
        """
        Kite basket margins return initial vs final blocks, each with 'total'.
        Prefer 'final' (spread / netting benefit); fall back to 'initial'.
        See https://kite.trade/docs/connect/v3/margins/
        """
        if margins is None:
            return None
        if isinstance(margins, dict) and isinstance(margins.get("data"), dict):
            margins = margins["data"]
        if not isinstance(margins, dict):
            return None

        def _block_total(block: Any) -> float | None:
            if not isinstance(block, dict):
                return None
            raw = block.get("total")
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        for key in ("final", "initial"):
            t = _block_total(margins.get(key))
            if t is not None and t > 0:
                return t

        legacy = margins.get("initial_margin")
        t = _block_total(legacy)
        if t is not None and t > 0:
            return t

        return None

    @staticmethod
    async def calculate_margin_and_lots(
        strategy: str, legs: dict, current_capital: float, index_name: str
    ) -> tuple[float, int, float]:
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
            
            lot_size = CapitalManager._lot_size_for_leg(leg_data, index_name)
            
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
            parsed = CapitalManager._total_from_kite_basket_response(margins)
            if parsed is not None:
                total_margin_per_lot_setup = parsed
            else:
                logger.error("FATAL: Broker returned invalid margin payload structure.")
                return 0.0, 0, 0.0
        except Exception as e:
            logger.error(f"FATAL: Broker margin check failed: {e}. Aborting trade.")
            return 0.0, 0, 0.0

        # Calculate maximum potential structural loss per lot
        lot_size = (
            CapitalManager._lot_size_for_leg(list(legs.values())[0], index_name) if legs else settings.NIFTY_LOT_SIZE
        )
        max_loss_per_lot = 0
        
        if strategy == "IRON_CONDOR":
            width_ce = abs(legs['sell_ce']['strike'] - legs['buy_ce']['strike'])
            width_pe = abs(legs['sell_pe']['strike'] - legs['buy_pe']['strike'])
            credit_ce = legs['sell_ce'].get('premium', 0) - legs['buy_ce'].get('premium', 0)
            credit_pe = legs['sell_pe'].get('premium', 0) - legs['buy_pe'].get('premium', 0)
            max_loss_ce = (width_ce - credit_ce) * lot_size
            max_loss_pe = (width_pe - credit_pe) * lot_size
            max_loss_per_lot = max(max_loss_ce, max_loss_pe)
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
        if (
            max_loss_per_lot <= 0
            or not math.isfinite(max_loss_per_lot)
        ):
            lots_by_loss = 0
        else:
            lots_by_loss = int(max_acceptable_loss // max_loss_per_lot)

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
    def approximate_margin(strategy: str, legs: dict, index_name: str) -> float:
        """Approximation based on spread width."""
        lot_size = (
            CapitalManager._lot_size_for_leg(list(legs.values())[0], index_name) if legs else settings.NIFTY_LOT_SIZE
        )
        
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
