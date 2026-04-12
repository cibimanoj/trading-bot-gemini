import asyncio

from engine.capital_manager import CapitalManager


def test_zero_max_loss_per_lot_yields_zero_lots(monkeypatch):
    async def fake_margins(*args, **kwargs):
        return {"data": {"final": {"total": 5000.0}}}

    from data.broker_fetcher import broker

    monkeypatch.setattr(broker, "get_margins", fake_margins)

    legs = {
        "buy_ce": {
            "tradingsymbol": "NIFTY24N22500CE",
            "strike": 22500,
            "premium": 0.0,
            "lot_size": 75,
        }
    }

    async def run():
        return await CapitalManager.calculate_margin_and_lots(
            "BUY_CE", legs, current_capital=100000.0, index_name="NIFTY"
        )

    margin, lots, _ = asyncio.run(run())
    assert lots == 0
    assert margin == 0
