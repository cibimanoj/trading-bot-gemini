from engine.regime import RegimeType

class Scorer:
    @staticmethod
    def score_setup(regime: RegimeType, bias: str, iv_percentile: float, pcr_zscore: float) -> int:
        """
        Creates a confidence score (0-100) based on convergence of indicators.
        Each factor generally adds 20 points.
        """
        score = 0
        
        # 1. Regime Clarity
        if regime in [RegimeType.TREND_STRONG, RegimeType.RANGE]:
            score += 20
        elif regime == RegimeType.TREND_MILD:
            score += 10
            
        # 2. Bias Clarity
        if bias in ["BULLISH", "BEARISH"]:
            score += 20
            
        # 3. IV Percentile logic (IV Rank)
        # If High IV (> 70) and RANGE, perfect for selling
        # If Low IV (< 30) and TREND, perfect for buying
        if regime == RegimeType.RANGE and iv_percentile > 70:
            score += 20
        elif regime == RegimeType.TREND_STRONG and iv_percentile < 30:
            score += 20
            
        # 4. PCR Z-Score confirmation
        # High PCR Z-Score corresponds to bullishness
        if bias == "BULLISH" and pcr_zscore > 1.5:
            score += 20
        elif bias == "BEARISH" and pcr_zscore < -1.5:
            score += 20
        elif abs(pcr_zscore) > 0.5:
            score += 10
            
        # 5. Volatility / Normalization check (bonus points if everything aligns nicely)
        if score >= 60:
            score += 20
            
        return min(score, 100)
