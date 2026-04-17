from enum import Enum

class RegimeType(Enum):
    TREND_STRONG = "TREND_STRONG"
    TREND_MILD = "TREND_MILD"
    RANGE = "RANGE"
    UNCLEAR = "UNCLEAR"

class MarketRegime:
    @staticmethod
    def determine_regime(adx_value: float, iv_percentile: float, pcr: float) -> RegimeType:
        """
        Regime from ADX (primary), with IV percentile and PCR as context when ADX is weak or borderline.
        """
        if adx_value <= 0:
            return RegimeType.UNCLEAR

        if adx_value > 25:
            return RegimeType.TREND_STRONG if adx_value > 30 else RegimeType.TREND_MILD

        # ADX <= 25: range / chop — IV percentile + PCR flag extremes with no clear credit-spread edge
        if iv_percentile < 15 and (pcr < 0.65 or pcr > 1.55):
            return RegimeType.UNCLEAR
        return RegimeType.RANGE

    @staticmethod
    def determine_directional_bias(dmp: float, dmn: float, pcr: float) -> str:
        """
        Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
        """
        # PCR interpretation here is non-contrarian:
        # - Higher PCR implies heavier put OI vs call OI (often bearish sentiment / hedging).
        # - Lower PCR implies heavier call OI vs put OI (often bullish sentiment).
        if dmp > dmn and pcr < 0.8:
            return "BULLISH"
        elif dmn > dmp and pcr > 1.2:
            return "BEARISH"
        return "NEUTRAL"
