from config import settings
from engine.regime import RegimeType
from engine.strategy_engine import StrategyEngine


def test_trend_directional_skips_high_iv():
    assert (
        StrategyEngine.select_strategy(RegimeType.TREND_STRONG, "BULLISH", 50.0)
        == "NO_TRADE"
    )


def test_trend_directional_allows_low_iv():
    low = settings.MAX_IV_PERCENTILE_FOR_DIRECTIONAL_LONG - 1
    assert StrategyEngine.select_strategy(RegimeType.TREND_STRONG, "BULLISH", low) == "BUY_CE"
