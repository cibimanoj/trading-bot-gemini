from db.database import db_instance
from engine.risk_manager import risk_manager
from typing import Optional

class PortfolioTracker:
    @staticmethod
    async def process_simulated_pl(pnl: float, is_win: bool) -> Optional[str]:
        """
        Updates the virtual capital based on simulated PnL and updates Risk State.
        Returns an alert string if Risk Mode changes, else None.
        """
        current = await db_instance.get_current_capital()
        new_capital = current + pnl
        if new_capital < 0:
            new_capital = 0.0
        await db_instance.update_capital(new_capital)
        # Calculate True Daily Drawdown
        sod_capital = await db_instance.get_sod_capital()
        if sod_capital <= 0:
            drawdown_pct = 0.0
        else:
            drawdown_pct = ((new_capital - sod_capital) / sod_capital) * 100.0
        # Update Risk Manager
        alert_msg = await risk_manager.update_after_trade(is_win=is_win, current_drawdown_pct=drawdown_pct)
        return alert_msg
        
    @staticmethod
    async def get_current_capital() -> float:
        return await db_instance.get_current_capital()
