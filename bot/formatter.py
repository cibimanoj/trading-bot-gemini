import json
def escape_md(text: str) -> str:
    """Escape markdown special characters for Telegram (Standard Markdown V1)."""
    # Standard Markdown in Telegram only rigidly breaks on _ , * , ` , [
    escape_chars = r"_*`["
    for c in escape_chars:
        text = str(text).replace(c, f"\\{c}")
    return text

class BotFormatter:
    @staticmethod
    def format_signal(signal: dict) -> str:
        """
        Formats the dictionary signal into the required alert Markdown structure.
        """
        conf_score = signal.get("confidence", 0)
        urgency = "🚨 HIGH PROBABILITY TRADE" if conf_score >= 80 else "⚡ TRADE ALERT"
        
        strategy_mapped = signal['strategy'].replace("_", " ").title()
        
        md = f"{urgency} ({conf_score}%)\n\n"
        md += f"Index: {escape_md(signal['index'])}\n"
        md += f"Market: {escape_md(signal['regime'])}\n\n"
        md += f"Strategy: {escape_md(strategy_mapped)}\n\n"
        
        md += "📌 Trades:\n"
        for leg_key, leg_config in signal['legs'].items():
            action = "Sell" if "sell" in leg_key else "Buy"
            type_flag = leg_config['type'].upper() + "E"
            md += f"{action} {leg_config['strike']} {type_flag} @ ₹{escape_md(str(leg_config['premium']))}\n"
            
        md += "\n💰 Capital:\n"
        
        cap_used = signal['capital_used']
        lots = signal['lots']
        current_cap = signal.get('current_capital', 0.0)
        md += f"Current: ₹{escape_md(f'{current_cap:,.2f}')}\n"
        md += f"Used: ₹{escape_md(f'{cap_used:,.2f}')}\n"
        md += f"Lots: {lots}\n\n"
        
        md += "🛡️ Stop-Loss:\n"
        for leg_key, leg_config in signal['legs'].items():
            type_flag = leg_config['type'].upper() + "E"
            md += f"{type_flag} SL: ₹{escape_md(str(leg_config['sl']))}\n"
            
        md += f"OR\n{escape_md(signal['spot_sl'])}\n\n"
        
        md += "🎯 Target:\n"
        md += f"{escape_md(signal['target_msg'])}\n\n"
        
        md += "⏱️ Exit:\n"
        md += f"{escape_md(signal['exit_time'])}\n\n"
        
        md += f"Confidence: {conf_score}%\n"
        return md
