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
        Determines the market regime based on ADX (trend strength) and IV percentile.
        - TREND_STRONG: ADX > 25
        - RANGE: ADX <= 25
        - IV adds context (high IV generally favors selling in a range, or break out in trend)
        """
        # A simple but effective classification
        if adx_value > 25:
            if adx_value > 30:
                return RegimeType.TREND_STRONG
            else:
                return RegimeType.TREND_MILD
        elif adx_value <= 25 and adx_value > 0:
            return RegimeType.RANGE
        else:
            return RegimeType.UNCLEAR

    @staticmethod
    def determine_directional_bias(dmp: float, dmn: float, pcr: float) -> str:
        """
        Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
        """
        if dmp > dmn and pcr > 1.2:
            return "BULLISH"
        elif dmn > dmp and pcr < 0.8:
            return "BEARISH"
        return "NEUTRAL"
