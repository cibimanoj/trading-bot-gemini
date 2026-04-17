from __future__ import annotations

from typing import Any


def escape_md(text: Any) -> str:
    """
    Escape Telegram "Markdown" (legacy / v1) special chars.

    We intentionally keep using legacy Markdown here because callers pass
    `parse_mode="Markdown"`; switching to MarkdownV2 would require broader
    escaping rules and could break existing formatting.
    """
    # Telegram legacy Markdown is particularly sensitive to these characters.
    s = "" if text is None else str(text)
    for c in r"_*`[":
        s = s.replace(c, f"\\{c}")
    return s

class BotFormatter:
    @staticmethod
    def format_signal(signal: dict) -> str:
        """
        Formats the dictionary signal into the required alert Markdown structure.
        """
        signal = signal or {}
        conf_score = int(signal.get("confidence") or 0)
        urgency = "🚨 HIGH PROBABILITY TRADE" if conf_score >= 80 else "⚡ TRADE ALERT"
        
        strategy_raw = signal.get("strategy") or "UNKNOWN_STRATEGY"
        strategy_mapped = str(strategy_raw).replace("_", " ").title()
        
        md = f"{urgency} ({conf_score}%)\n\n"
        md += f"Index: {escape_md(signal.get('index') or 'UNKNOWN')}\n"
        md += f"Market: {escape_md(signal.get('regime') or 'UNKNOWN')}\n\n"
        md += f"Strategy: {escape_md(strategy_mapped)}\n\n"
        
        md += "📌 Trades:\n"
        legs = signal.get("legs") or {}
        if isinstance(legs, dict) and legs:
            for leg_key, leg_config in legs.items():
                leg_config = leg_config or {}
                action = "Sell" if "sell" in str(leg_key).lower() else "Buy"
                raw_type = (leg_config.get("type") or "").strip().lower()
                type_flag = (raw_type.upper() + "E") if raw_type in ("c", "p") else "OPT"
                strike = leg_config.get("strike", "?")
                premium = leg_config.get("premium", "?")
                md += f"{action} {escape_md(strike)} {escape_md(type_flag)} @ ₹{escape_md(premium)}\n"
        else:
            md += "No legs available.\n"
            
        md += "\n💰 Capital:\n"
        
        cap_used = signal.get("capital_used") or 0.0
        lots = signal.get("lots") or 0
        current_cap = signal.get("current_capital") or 0.0
        try:
            md += f"Current: ₹{escape_md(f'{float(current_cap):,.2f}')}\n"
        except (TypeError, ValueError):
            md += f"Current: ₹{escape_md(current_cap)}\n"
        try:
            md += f"Used: ₹{escape_md(f'{float(cap_used):,.2f}')}\n"
        except (TypeError, ValueError):
            md += f"Used: ₹{escape_md(cap_used)}\n"
        md += f"Lots: {escape_md(lots)}\n\n"
        
        md += "🛡️ Stop-Loss:\n"
        if isinstance(legs, dict) and legs:
            for _, leg_config in legs.items():
                leg_config = leg_config or {}
                raw_type = (leg_config.get("type") or "").strip().lower()
                type_flag = (raw_type.upper() + "E") if raw_type in ("c", "p") else "OPT"
                md += f"{escape_md(type_flag)} SL: ₹{escape_md(leg_config.get('sl', '?'))}\n"
            
        md += f"OR\n{escape_md(signal.get('spot_sl') or '')}\n\n"
        
        md += "🎯 Target:\n"
        md += f"{escape_md(signal.get('target_msg') or '')}\n\n"
        
        md += "⏱️ Exit:\n"
        md += f"{escape_md(signal.get('exit_time') or '')}\n\n"
        
        md += f"Confidence: {conf_score}%\n"
        return md
