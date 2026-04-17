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
            
        # 4. PCR Z-Score (rolling statistical z; not the same bucket as bias PCR thresholds)
        # With PCR used as a bearish-when-high metric (see MarketRegime.determine_directional_bias),
        # bullish confirmations correspond to unusually LOW PCR, and bearish to unusually HIGH PCR.
        if bias == "BULLISH" and pcr_zscore < -1.0:
            score += 18
        elif bias == "BEARISH" and pcr_zscore > 1.0:
            score += 18
        elif abs(pcr_zscore) > 0.35:
            score += 8
            
        # 5. Tight bonus — avoid inflating marginal setups
        if score >= 78:
            score += min(12, 100 - score)
            
        return min(score, 100)
