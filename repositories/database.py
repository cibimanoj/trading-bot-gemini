import json
import logging
import sqlite3

import aiosqlite

from config import settings
from typing import Optional

logger = logging.getLogger(__name__)

# Register SQLite adapters and converters for JSON dicts
sqlite3.register_adapter(dict, json.dumps)
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_converter("JSON", json.loads)


class Database:
    def __init__(self):
        self.db_path = settings.DB_PATH

    def _connect(self):
        return aiosqlite.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

    async def init_db(self):
        async with self._connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            # Create signals table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    index_name TEXT,
                    market_regime TEXT,
                    strategy_type TEXT,
                    trade_details JSON,
                    entry_capital REAL,
                    confidence_score INTEGER
                )
            """)

            # Create portfolio state table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_capital REAL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Initialize capital if empty
            async with db.execute("SELECT current_capital FROM portfolio ORDER BY id DESC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                if row is None:
                    await db.execute(
                        "INSERT INTO portfolio (current_capital) VALUES (?)",
                        (settings.INITIAL_CAPITAL,)
                    )
            # Create risk state persistence table (Atomic single-row table)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS risk_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    mode TEXT,
                    wins INTEGER,
                    losses INTEGER,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    index_name TEXT NOT NULL,
                    pcr REAL,
                    avg_iv REAL,
                    iv_percentile REAL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_index_name ON market_snapshots(index_name)"
            )

            await db.commit()
            logger.info("Database initialized.")

    async def update_risk_state(self, mode: str, wins: int, losses: int):
        async with self._connect() as db:
            await db.execute("""
                INSERT INTO risk_state (id, mode, wins, losses, updated_at)
                VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                mode=excluded.mode, wins=excluded.wins, losses=excluded.losses, updated_at=CURRENT_TIMESTAMP
            """, (mode, wins, losses))
            await db.commit()

    async def get_risk_state(self) -> Optional[dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM risk_state WHERE id = 1") as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def save_signal(self, index_name: str, regime: str, strategy: str, details: dict, capital_used: float, confidence: int):
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO signals (index_name, market_regime, strategy_type, trade_details, entry_capital, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (index_name, regime, strategy, details, capital_used, confidence)
            )
            await db.commit()

    async def get_current_capital(self) -> float:
        async with self._connect() as db:
            async with db.execute("SELECT current_capital FROM portfolio ORDER BY id DESC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else settings.INITIAL_CAPITAL

    async def get_sod_capital(self) -> float:
        """
        Fetch the Start of Day (SOD) capital.
        Mathematically targets the last chronological capital value structurally committed BEFORE today.
        This flawlessly eliminates 'Drawdown Amnesia' and guarantees perfect baseline comparison.
        """
        async with self._connect() as db:
            query = """
                SELECT current_capital FROM portfolio
                WHERE date(updated_at, '+5 hours', '+30 minutes') < date('now', '+5 hours', '+30 minutes')
                ORDER BY updated_at DESC LIMIT 1
            """
            async with db.execute(query) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]

            # If no backwards trades technically exist (first day of the bot operating), return the exact absolute foundation.
            query_prev = "SELECT current_capital FROM portfolio ORDER BY id ASC LIMIT 1"
            async with db.execute(query_prev) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else settings.INITIAL_CAPITAL

    async def update_capital(self, new_capital: float):
        async with self._connect() as db:
            await db.execute("INSERT INTO portfolio (current_capital) VALUES (?)", (new_capital,))
            await db.commit()

    async def get_recent_signals(self, limit: int = 5):
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                # Convert sqlite3.Row to dict
                return [dict(row) for row in rows]

    async def insert_market_snapshot(
        self, index_name: str, pcr: float, avg_iv: float, iv_percentile: float
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO market_snapshots (index_name, pcr, avg_iv, iv_percentile)
                VALUES (?, ?, ?, ?)
                """,
                (index_name, pcr, avg_iv, iv_percentile),
            )
            await db.commit()

    async def get_recent_pcr_values(self, index_name: str, limit: int) -> list[float]:
        """Oldest-first PCR values from recent snapshots (excludes rows not yet written this tick)."""
        async with self._connect() as db:
            async with db.execute(
                """
                SELECT pcr FROM market_snapshots
                WHERE index_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (index_name, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        vals = [float(r[0]) for r in reversed(rows) if r[0] is not None]
        return vals

    async def get_recent_avg_iv_values(self, index_name: str, limit: int) -> list[float]:
        """Oldest-first average IV values for rolling IV rank."""
        async with self._connect() as db:
            async with db.execute(
                """
                SELECT avg_iv FROM market_snapshots
                WHERE index_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (index_name, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        vals = [float(r[0]) for r in reversed(rows) if r[0] is not None]
        return vals

    async def prune_old_rows(self) -> None:
        """
        Limit table growth: old snapshots/signals by age; portfolio by max row count (keeps newest).
        Safe to call periodically (e.g. once per day).
        """
        snap_days = settings.DB_PRUNE_MARKET_SNAPSHOT_DAYS
        sig_days = settings.DB_PRUNE_SIGNALS_DAYS
        max_portfolio = settings.DB_PORTFOLIO_MAX_ROWS
        async with self._connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM market_snapshots WHERE timestamp < datetime('now', '-' || ? || ' days')",
                (snap_days,)
            )
            await db.execute(
                "DELETE FROM signals WHERE timestamp < datetime('now', '-' || ? || ' days')",
                (sig_days,)
            )
            await db.execute(
                """
                DELETE FROM portfolio
                WHERE id < COALESCE(
                    (SELECT MIN(id) FROM (
                        SELECT id FROM portfolio ORDER BY id DESC LIMIT ?
                    )),
                    0
                )
                """,
                (max_portfolio,),
            )
            await db.commit()
        logger.info(
            "DB prune completed (snapshots ≥%sd, signals ≥%sd, portfolio cap %s rows).",
            snap_days,
            sig_days,
            max_portfolio,
        )


db_instance = Database()
