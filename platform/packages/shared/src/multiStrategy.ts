import { atr, bollingerBands, rsi, vwap } from "./indicators.js";
import { evaluateRules, extractMlFeatures } from "./strategy.js";
import type { Candle, MarketRegime, Side, StrategyCandidate, StrategyId } from "./types.js";

function last<T>(arr: T[]): T | undefined {
  return arr[arr.length - 1];
}

function percentileRank(values: number[], x: number): number {
  if (values.length === 0) return 0.5;
  const sorted = [...values].sort((a, b) => a - b);
  let below = 0;
  for (const v of sorted) {
    if (v < x) below += 1;
  }
  return below / sorted.length;
}

/** VWAP mean reversion: fade stretched closes vs VWAP with RSI filter */
export function evaluateMeanReversion(candles: Candle[]): {
  candidate: StrategyCandidate | null;
} {
  if (candles.length < 55) return { candidate: null };

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const vols = candles.map((c) => c.volume);
  const rsi14 = rsi(closes, 14);
  const vw = vwap(highs, lows, closes, vols);
  const atr14 = atr(highs, lows, closes, 14);
  const i = closes.length - 1;
  const atrVal = last(atr14) ?? highs[i] - lows[i];
  const dev = 0.45 * atrVal;
  const rsiVal = rsi14[i];
  const c = closes[i];
  const v = vw[i];

  let action: Side = "NO_TRADE";
  const reasons: string[] = [];
  let score = 42;

  if (c < v - dev && rsiVal < 40) {
    action = "BUY";
    reasons.push("Below VWAP stretch", `RSI ${rsiVal.toFixed(0)}`);
    score += 28;
  } else if (c > v + dev && rsiVal > 60) {
    action = "SELL";
    reasons.push("Above VWAP stretch", `RSI ${rsiVal.toFixed(0)}`);
    score += 28;
  }

  if (action === "NO_TRADE") return { candidate: null };

  const entry = c;
  const stopDist = Math.max(atrVal * 1.25, entry * 0.0035);
  const stopLoss = action === "BUY" ? entry - stopDist : entry + stopDist;
  const target = action === "BUY" ? entry + stopDist * 1.4 : entry - stopDist * 1.4;
  const symbol = candles[i].symbol;
  const features = extractMlFeatures(candles, 1);

  return {
    candidate: {
      strategyId: "mean_reversion_vwap",
      suggestion: {
        symbol,
        action,
        entry: Math.round(entry * 100) / 100,
        stopLoss: Math.round(stopLoss * 100) / 100,
        target: Math.round(target * 100) / 100,
        reason: reasons,
        timeframe: "1m",
      },
      ruleScore: Math.min(100, score),
      features,
    },
  };
}

/** Post-squeeze breakout: Bollinger width in lower quartile then close outside bands */
export function evaluateVolatilityBreakout(candles: Candle[]): {
  candidate: StrategyCandidate | null;
} {
  if (candles.length < 60) return { candidate: null };

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const { upper, lower, width } = bollingerBands(closes, 20, 2);
  const atr14 = atr(highs, lows, closes, 14);
  const i = closes.length - 1;
  const atrVal = last(atr14) ?? highs[i] - lows[i];

  const hist = width.slice(25, i);
  const wNow = width[i];
  if (hist.length < 10 || wNow <= 0) return { candidate: null };

  const rank = percentileRank(hist, wNow);
  const squeeze = rank < 0.35;

  let action: Side = "NO_TRADE";
  const reasons: string[] = [];
  let score = 40;

  if (squeeze && closes[i] > upper[i]) {
    action = "BUY";
    reasons.push("BB squeeze → close above upper");
    score += 32;
  } else if (squeeze && closes[i] < lower[i]) {
    action = "SELL";
    reasons.push("BB squeeze → close below lower");
    score += 32;
  } else if (closes[i] > upper[i] * 1.001) {
    action = "BUY";
    reasons.push("Close above upper band");
    score += 22;
  } else if (closes[i] < lower[i] * 0.999) {
    action = "SELL";
    reasons.push("Close below lower band");
    score += 22;
  }

  if (action === "NO_TRADE") return { candidate: null };

  const entry = closes[i];
  const stopDist = Math.max(atrVal * 1.35, entry * 0.004);
  const stopLoss = action === "BUY" ? entry - stopDist : entry + stopDist;
  const target = action === "BUY" ? entry + stopDist * 1.8 : entry - stopDist * 1.8;
  const symbol = candles[i].symbol;
  const features = extractMlFeatures(candles, 1);

  return {
    candidate: {
      strategyId: "volatility_breakout",
      suggestion: {
        symbol,
        action,
        entry: Math.round(entry * 100) / 100,
        stopLoss: Math.round(stopLoss * 100) / 100,
        target: Math.round(target * 100) / 100,
        reason: reasons,
        timeframe: "1m",
      },
      ruleScore: Math.min(100, score),
      features,
    },
  };
}

const REGIME_STRATEGIES: Record<MarketRegime, StrategyId[]> = {
  TRENDING_UP: ["trend_ema", "volatility_breakout"],
  TRENDING_DOWN: ["trend_ema", "volatility_breakout"],
  SIDEWAYS: ["mean_reversion_vwap"],
  HIGH_VOLATILITY: ["volatility_breakout", "trend_ema"],
  LOW_VOLATILITY: ["mean_reversion_vwap", "trend_ema"],
};

export function strategiesForRegime(regime: MarketRegime): StrategyId[] {
  return REGIME_STRATEGIES[regime];
}

export function runStrategiesForRegime(
  regime: MarketRegime,
  candles: Candle[],
): StrategyCandidate[] {
  const allowed = new Set(strategiesForRegime(regime));
  const out: StrategyCandidate[] = [];

  if (allowed.has("trend_ema")) {
    const { suggestion, ruleScore, features } = evaluateRules({ candles });
    if (suggestion && suggestion.action !== "NO_TRADE") {
      out.push({
        strategyId: "trend_ema",
        suggestion,
        ruleScore,
        features,
      });
    }
  }

  if (allowed.has("mean_reversion_vwap")) {
    const { candidate } = evaluateMeanReversion(candles);
    if (candidate) out.push(candidate);
  }

  if (allowed.has("volatility_breakout")) {
    const { candidate } = evaluateVolatilityBreakout(candles);
    if (candidate) out.push(candidate);
  }

  return out;
}

export function pickBestCandidate(candidates: StrategyCandidate[]): StrategyCandidate | null {
  if (candidates.length === 0) return null;
  const priority: StrategyId[] = ["trend_ema", "volatility_breakout", "mean_reversion_vwap"];
  return [...candidates].sort((a, b) => {
    if (b.ruleScore !== a.ruleScore) return b.ruleScore - a.ruleScore;
    return priority.indexOf(a.strategyId) - priority.indexOf(b.strategyId);
  })[0];
}
