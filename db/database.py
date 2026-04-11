import aiosqlite
import logging
import sqlite3
import json

logger = logging.getLogger(__name__)

from config import settings

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
            
    async def get_risk_state(self) -> dict | None:
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

# Global database instance
db_instance = Database()
