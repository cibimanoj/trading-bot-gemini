from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import telegram_chat_ids
from db.database import db_instance
from engine.portfolio_tracker import PortfolioTracker

router = Router()


def _telegram_chat_allowed(message: Message) -> bool:
    """Only configured Telegram chat id(s) may use bot commands (comma-separated TELEGRAM_CHAT_ID)."""
    allowed = telegram_chat_ids()
    if not allowed:
        return False
    return message.chat.id in allowed


async def _require_allowed_chat(message: Message) -> bool:
    """Returns True if the handler should continue; otherwise replies and returns False."""
    if _telegram_chat_allowed(message):
        return True
    await message.answer("Not authorized.")
    return False


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not await _require_allowed_chat(message):
        return
    welcome_msg = (
        "🤖 **Headless Options Engine Started**\n\n"
        "I am monitoring NIFTY and BANKNIFTY.\n"
        "I will send high-probability alerts based on quantitative signals.\n\n"
        "Available commands:\n"
        "/status - Check current setup and capital\n"
        "/signals - List recent signals\n"
        "/history - Show trade history"
    )
    await message.answer(welcome_msg, parse_mode="Markdown")

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not await _require_allowed_chat(message):
        return
    capital = await PortfolioTracker.get_current_capital()
    status_msg = (
        "📊 **Engine Status**\n\n"
        f"✅ Engine: RUNNING\n"
        f"✅ Data Poller: ACTIVE (IST)\n"
        f"💰 Virtual Capital: ₹{capital:,.2f}\n"
    )
    await message.answer(status_msg, parse_mode="Markdown")

@router.message(Command("signals"))
@router.message(Command("history"))
async def cmd_history(message: Message):
    if not await _require_allowed_chat(message):
        return
    signals = await db_instance.get_recent_signals(limit=5)
    if not signals:
        await message.answer("No recent signals found.")
        return
        
    hist_msg = "📜 **Recent Signals**\n\n"
    for sig in signals:
        hist_msg += (
            f"🔸 {sig['timestamp']} | {sig['index_name']} | {sig['strategy_type']}\n"
            f"Regime: {sig['market_regime']} | Score: {sig['confidence_score']}%\n\n"
        )
    await message.answer(hist_msg, parse_mode="Markdown")

@router.message(Command("simulate_pl"))
async def cmd_simulate_pl(message: Message):
    if not await _require_allowed_chat(message):
        return
    try:
        parts = (message.text or "").split()
        if len(parts) < 3:
            await message.answer("Usage: /simulate_pl <amount> <win|loss>")
            return
        pnl = float(parts[1])
        is_win = parts[2].lower() == "win"
        
        alert_msg = await PortfolioTracker.process_simulated_pl(pnl, is_win)
        
        await message.answer(f"Simulated P&L of ₹{pnl}. Win={is_win}")
        if alert_msg:
            await message.answer(alert_msg)
            
    except Exception:
        await message.answer("Usage: /simulate_pl <amount> <win|loss>")
