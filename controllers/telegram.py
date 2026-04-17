import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import telegram_chat_ids
from db.database import db_instance
from engine.portfolio_tracker import PortfolioTracker
from services.self_check import run_self_check, format_self_check_markdown

router = Router()
logger = logging.getLogger(__name__)


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
    uid = message.from_user.id if message.from_user else None
    logger.warning(
        "Unauthorized Telegram command blocked (chat_id=%s, user_id=%s)",
        message.chat.id,
        uid,
    )
    await message.answer("This bot is private. Access denied.")
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
        try:
            pnl = float(parts[1])
        except ValueError:
            await message.answer("Amount must be a number. Usage: /simulate_pl <amount> <win|loss>")
            return
        win_arg = parts[2].lower()
        if win_arg not in ["win", "loss"]:
            await message.answer("Usage: /simulate_pl <amount> <win|loss>")
            return

        is_win = win_arg == "win"
        if not is_win:
            pnl = -abs(pnl)

        alert_msg = await PortfolioTracker.process_simulated_pl(pnl, is_win)

        await message.answer(f"Simulated P&L of ₹{pnl}. Win={is_win}")
        if alert_msg:
            await message.answer(alert_msg)

    except Exception:
        logger.exception("simulate_pl failed")
        await message.answer("Could not apply simulated P&L. Try again or check logs.")


@router.message(Command("selfcheck"))
async def cmd_selfcheck(message: Message):
    if not await _require_allowed_chat(message):
        return
    try:
        report = await run_self_check()
        await message.answer(format_self_check_markdown(report), parse_mode="Markdown")
    except Exception:
        logger.exception("selfcheck failed")
        await message.answer("Self-check failed. Check logs.")

