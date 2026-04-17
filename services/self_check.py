import logging

from data.broker_fetcher import broker

logger = logging.getLogger(__name__)


async def run_self_check() -> dict:
    """
    Lightweight runtime validation:
    - instrument master fetch works
    - key columns exist
    - NIFTY/BANKNIFTY/VIX instrument tokens resolve from master

    Returns a dict suitable for logging or Telegram output.
    """
    result: dict = {
        "ok": True,
        "instrument_rows": 0,
        "missing_columns": [],
        "tokens": {"NIFTY_50": None, "NIFTY_BANK": None, "INDIA_VIX": None},
        "notes": [],
    }

    try:
        df = await broker.get_instruments()
    except Exception as e:
        result["ok"] = False
        result["notes"].append(f"instrument master fetch failed: {e}")
        return result

    if df is None or getattr(df, "empty", True):
        result["ok"] = False
        result["notes"].append("instrument master is empty")
        return result

    result["instrument_rows"] = int(getattr(df, "shape", [0])[0] or 0)

    required = {"exchange", "tradingsymbol", "instrument_token"}
    missing = sorted(list(required - set(getattr(df, "columns", []))))
    if missing:
        result["ok"] = False
        result["missing_columns"] = missing
        result["notes"].append("instrument master missing required columns")
        return result

    def _resolve(exchange: str, ts: str) -> int | None:
        try:
            sub = df[(df["exchange"] == exchange) & (df["tradingsymbol"] == ts)]
            if sub.empty:
                return None
            tok = int(sub.iloc[0]["instrument_token"])
            return tok if tok > 0 else None
        except Exception:
            return None

    result["tokens"]["NIFTY_50"] = _resolve("NSE", "NIFTY 50")
    result["tokens"]["NIFTY_BANK"] = _resolve("NSE", "NIFTY BANK")
    result["tokens"]["INDIA_VIX"] = _resolve("NSE", "INDIA VIX")

    if not result["tokens"]["NIFTY_50"]:
        result["ok"] = False
        result["notes"].append("could not resolve NSE:NIFTY 50 token")
    if not result["tokens"]["NIFTY_BANK"]:
        result["ok"] = False
        result["notes"].append("could not resolve NSE:NIFTY BANK token")
    if not result["tokens"]["INDIA_VIX"]:
        result["notes"].append("could not resolve NSE:INDIA VIX token (VIX percentile will be disabled)")

    return result


def format_self_check_markdown(report: dict) -> str:
    ok = bool(report.get("ok"))
    rows = report.get("instrument_rows")
    tokens = report.get("tokens") or {}
    notes = report.get("notes") or []

    status = "✅ SELF-CHECK OK" if ok else "❌ SELF-CHECK FAILED"
    lines = [
        f"🧪 **{status}**",
        "",
        f"Instrument rows: `{rows}`",
        "",
        "**Resolved tokens**",
        f"- NIFTY 50: `{tokens.get('NIFTY_50')}`",
        f"- NIFTY BANK: `{tokens.get('NIFTY_BANK')}`",
        f"- INDIA VIX: `{tokens.get('INDIA_VIX')}`",
    ]
    if notes:
        lines += ["", "**Notes**"] + [f"- {n}" for n in notes]
    return "\n".join(lines)

