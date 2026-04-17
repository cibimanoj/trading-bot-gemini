from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TradeMode(Enum):
    NORMAL = "Normal"
    RECOVERY = "Recovery"
    HALTED = "Halted"

class RiskManager:
    def __init__(self):
        self.mode = TradeMode.NORMAL
        self.consecutive_wins = 0
        self.consecutive_losses = 0

    def adjust_lot_size(self, base_lots: int) -> int:
        """
        Adjusts lot size based on current TradeMode.
        Returns: Adjusted lot size.
        """
        if base_lots == 0 or self.mode == TradeMode.HALTED:
            return 0
        elif self.mode == TradeMode.RECOVERY:
            # Half size, minimum 1
            return max(1, base_lots // 2)
        return base_lots

    async def update_after_trade(self, is_win: bool, current_drawdown_pct: float) -> str | None:
        """
        Evaluates risk state based on the latest trade outcome and daily drawdown.
        Returns a string alert if the mode changed, otherwise None.
        """
        old_mode = self.mode

        # 1. Circuit Breaker Hook
        if current_drawdown_pct <= -2.0:
            self.mode = TradeMode.HALTED
            await self._persist_state()
            if old_mode != TradeMode.HALTED:
                return (
                    "🚫 KILL SWITCH: Daily max drawdown reached (≤ -2%). "
                    "Trading halted for today; close any live positions manually if applicable."
                )
            return None

        # 2. State Machine Transitions
        if self.mode == TradeMode.NORMAL:
            if is_win:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_wins = 0
                self.consecutive_losses += 1
                
                # Check for recovery trigger
                if current_drawdown_pct <= -1.0 or self.consecutive_losses >= 2:
                    self.mode = TradeMode.RECOVERY

        elif self.mode == TradeMode.RECOVERY:
            if is_win:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                
                # Exit recovery condition
                if self.consecutive_wins >= 2 or current_drawdown_pct >= -0.5:
                    self.mode = TradeMode.NORMAL
            else:
                self.consecutive_wins = 0
                self.consecutive_losses += 1

        await self._persist_state()

        # Check if mode changed
        if old_mode != self.mode:
            if self.mode == TradeMode.RECOVERY:
                return "⚠️ RECOVERY MODE: Loss threshold hit. Strategy proving required."
            elif self.mode == TradeMode.NORMAL:
                return "✅ NORMAL MODE: Recovery successful. Resuming full lot size."

        return None

    async def _persist_state(self):
        from db.database import db_instance
        await db_instance.update_risk_state(self.mode.value, self.consecutive_wins, self.consecutive_losses)

    async def hydrate_state(self):
        """Pulls the exact state from SQLite on server launch, curing memory amnesia."""
        from db.database import db_instance
        state = await db_instance.get_risk_state()
        if state:
            try:
                self.mode = TradeMode(state['mode'])
            except ValueError:
                self.mode = TradeMode.NORMAL
            self.consecutive_wins = state['wins']
            self.consecutive_losses = state['losses']
            logger.info(f"Risk state rehydrated from DB: {self.mode.name}")
            
    async def try_midnight_flush(self) -> bool:
        """
        Mechanically resets the state machine if a new trading day has dawned.
        Returns True if a flush occurred.
        """
        from db.database import db_instance
        from utils.timezone import TimezoneNormalizer
        
        state = await db_instance.get_risk_state()
        if not state or not state['updated_at']:
            return False
            
        from utils.sqlite_time import parse_sqlite_utc_timestamp
        try:
            last_dt = parse_sqlite_utc_timestamp(state.get("updated_at"))
            if last_dt is None:
                return False
            current_ist = TimezoneNormalizer.now_ist_aware()
            last_ist = last_dt.astimezone(TimezoneNormalizer.IST)
            
            # If the calendar day shifted in India, execute the flush
            if current_ist.date() > last_ist.date():
                self.mode = TradeMode.NORMAL
                self.consecutive_wins = 0
                self.consecutive_losses = 0
                await self._persist_state()
                logger.info("Midnight Flush executed. Risk state reset to NORMAL.")
                return True
        except Exception as e:
            logger.error(f"Midnight flush parsing failed: {e}")
        return False

    async def sync_drawdown_from_portfolio(self) -> str | None:
        """
        Apply daily drawdown limits from current DB capital vs SOD — no trade event required.
        Use when capital changes outside /simulate_pl (e.g. future broker sync) or on a schedule.
        """
        from db.database import db_instance

        current = await db_instance.get_current_capital()
        sod = await db_instance.get_sod_capital()
        if sod <= 0:
            return None

        dd_pct = ((current - sod) / sod) * 100.0
        old_mode = self.mode

        if dd_pct <= -2.0:
            self.mode = TradeMode.HALTED
            await self._persist_state()
            if old_mode != TradeMode.HALTED:
                return (
                    "🚫 KILL SWITCH: Daily max drawdown reached (≤ -2%). "
                    "Trading halted for today; close any live positions manually if applicable."
                )
            return None

        if self.mode == TradeMode.HALTED:
            return None

        if self.mode == TradeMode.NORMAL and dd_pct <= -1.0:
            self.mode = TradeMode.RECOVERY
            await self._persist_state()
            if old_mode == TradeMode.NORMAL:
                return "⚠️ RECOVERY MODE: Drawdown threshold hit. Strategy proving required."
            return None

        if self.mode == TradeMode.RECOVERY and dd_pct >= -0.5:
            self.mode = TradeMode.NORMAL
            self.consecutive_wins = 0
            self.consecutive_losses = 0
            await self._persist_state()
            if old_mode == TradeMode.RECOVERY:
                return "✅ NORMAL MODE: Drawdown recovered. Resuming full lot size."

        return None

# Global Risk Manager Instance
risk_manager = RiskManager()
