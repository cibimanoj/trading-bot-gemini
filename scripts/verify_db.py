"""Development helper: smoke-test SQLite repository wiring (run from repo root: python scripts/verify_db.py)."""

import asyncio

from db.database import db_instance


async def main():
    await db_instance.init_db()
    await db_instance.update_risk_state("NORMAL", 0, 0)
    state = await db_instance.get_risk_state()
    if state:
        print("Risk State updatedAt:", type(state["updated_at"]), state["updated_at"])

    await db_instance.save_signal("NIFTY", "RANGE", "IRON_CONDOR", {}, 0.0, 80)
    signals = await db_instance.get_recent_signals(1)
    if signals:
        print("Signal timestamp:", type(signals[0]["timestamp"]), signals[0]["timestamp"])


if __name__ == "__main__":
    asyncio.run(main())
