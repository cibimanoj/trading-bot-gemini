import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load from .env file if present
load_dotenv()

class Settings(BaseSettings):
    # Kite API config
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_ACCESS_TOKEN: str = os.getenv("KITE_ACCESS_TOKEN", "")

    # Telegram config
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Capital Management
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "50000.0"))
    MAX_CAPITAL_USE: float = 0.70  # Max 70% capital use per trade
    MAX_LOSS_CAPITAL_PCT: float = 0.05  # Max loss per trade = 5% of capital
    
    # Options & Strategy
    RISK_FREE_RATE: float = float(os.getenv("RISK_FREE_RATE", "0.065"))
    MIN_CONFIDENCE_SCORE: int = 75

    # Market data quality (seconds; Kite quote timestamps are naive IST-like)
    QUOTE_STALE_SPOT_SEC: float = float(os.getenv("QUOTE_STALE_SPOT_SEC", "15"))
    QUOTE_STALE_NFO_SEC: float = float(os.getenv("QUOTE_STALE_NFO_SEC", "180"))

    # Rolling history for PCR z-score and IV rank when VIX history is missing
    MARKET_SNAPSHOT_LOOKBACK: int = int(os.getenv("MARKET_SNAPSHOT_LOOKBACK", "80"))

    # Exchange lot sizes (override if contract size changes; used when instrument row has no lot_size)
    NIFTY_LOT_SIZE: int = int(os.getenv("NIFTY_LOT_SIZE", "75"))
    BANKNIFTY_LOT_SIZE: int = int(os.getenv("BANKNIFTY_LOT_SIZE", "15"))
    
    # DB configuration
    DB_PATH: str = os.getenv("DB_PATH", "sqlite.db")
    # Retention: prune on a schedule (see db.database.prune_old_rows)
    DB_PRUNE_MARKET_SNAPSHOT_DAYS: int = int(os.getenv("DB_PRUNE_MARKET_SNAPSHOT_DAYS", "45"))
    DB_PRUNE_SIGNALS_DAYS: int = int(os.getenv("DB_PRUNE_SIGNALS_DAYS", "365"))
    DB_PORTFOLIO_MAX_ROWS: int = int(os.getenv("DB_PORTFOLIO_MAX_ROWS", "3000"))

    # Trend long options: align with Scorer (cheap IV) — skip directional buys when "IV rank" is too high
    MAX_IV_PERCENTILE_FOR_DIRECTIONAL_LONG: float = float(
        os.getenv("MAX_IV_PERCENTILE_FOR_DIRECTIONAL_LONG", "35")
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()


def telegram_chat_ids() -> list[int]:
    """Comma-separated TELEGRAM_CHAT_ID values (e.g. private chat + group)."""
    raw = (settings.TELEGRAM_CHAT_ID or "").strip()
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out
