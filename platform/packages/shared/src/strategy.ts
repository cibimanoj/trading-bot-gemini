import { atr, ema, rsi, volumeSma, vwap } from "./indicators.js";
import type { Candle, TradeSuggestion, Side } from "./types.js";

export interface StrategyInputs {
  candles: Candle[];
}

function last<T>(arr: T[]): T | undefined {
  return arr[arr.length - 1];
}

/** Feature row for ML / orchestration: RSI, EMA spread, volume ratio, PCR (0.3–1.5). */
export function extractMlFeatures(candles: Candle[], pcr: number): number[] {
  if (candles.length < 55) {
    return [50, 0, 1, Math.min(1.5, Math.max(0.3, pcr))];
  }
  const closes = candles.map((c) => c.close);
  const vols = candles.map((c) => c.volume);
  const e9 = ema(closes, 9);
  const e21 = ema(closes, 21);
  const rsi14 = rsi(closes, 14);
  const volSma20 = volumeSma(vols, 20);
  const i = closes.length - 1;
  const rsiVal = rsi14[i];
  const emaSpread = (e9[i] - e21[i]) / (closes[i] || 1);
  const volRatio = volSma20[i] > 0 ? vols[i] / volSma20[i] : 1;
  return [rsiVal, emaSpread, volRatio, Math.min(1.5, Math.max(0.3, pcr))];
}

/**
 * Rule engine: EMA(9/21/50) crossover + RSI confirmation,
 * breakout vs recent range, volume spike vs SMA.
 */
export function evaluateRules(input: StrategyInputs): {
  suggestion: Omit<
    TradeSuggestion,
    "generatedAt" | "confidence" | "mlScore" | "mlLabel" | "ruleScore"
  > | null;
  ruleScore: number;
  features: number[];
} {
  const { candles } = input;
  if (candles.length < 55) {
    return { suggestion: null, ruleScore: 0, features: [50, 0, 1, 0.8] };
  }

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const vols = candles.map((c) => c.volume);

  const e9 = ema(closes, 9);
  const e21 = ema(closes, 21);
  const e50 = ema(closes, 50);
  const rsi14 = rsi(closes, 14);
  const vw = vwap(highs, lows, closes, vols);
  const atr14 = atr(highs, lows, closes, 14);
  const volSma20 = volumeSma(vols, 20);

  const i = closes.length - 1;
  const prev = i - 1;

  const crossUp = e9[prev] <= e21[prev] && e9[i] > e21[i];
  const crossDown = e9[prev] >= e21[prev] && e9[i] < e21[i];
  const trendLong = e21[i] > e50[i];
  const trendShort = e21[i] < e50[i];

  const rsiVal = rsi14[i];
  const rsiBull = rsiVal > 52 && rsiVal < 72;
  const rsiBear = rsiVal < 48 && rsiVal > 28;

  const recentHigh = Math.max(...highs.slice(-20));
  const recentLow = Math.min(...lows.slice(-20));
  const breakoutUp = closes[i] > recentHigh * 0.999;
  const breakoutDown = closes[i] < recentLow * 1.001;

  const volSpike = vols[i] > volSma20[i] * 1.35;

  let action: Side = "NO_TRADE";
  const reasons: string[] = [];
  let score = 40;

  if (crossUp && trendLong && rsiBull) {
    action = "BUY";
    reasons.push("EMA crossover (9/21)", "RSI strength", trendLong ? "Trend aligned (21>50)" : "");
    score += 25;
  } else if (crossDown && trendShort && rsiBear) {
    action = "SELL";
    reasons.push("EMA cross down", "RSI weakness", trendShort ? "Trend aligned (21<50)" : "");
    score += 25;
  }

  if (breakoutUp && action === "BUY") {
    reasons.push("Breakout vs 20-bar range");
    score += 10;
  }
  if (breakoutDown && action === "SELL") {
    reasons.push("Breakdown vs 20-bar range");
    score += 10;
  }

  if (volSpike && action !== "NO_TRADE") {
    reasons.push("Volume spike validation");
    score += 10;
  }

  if (closes[i] > vw[i] && action === "BUY") {
    reasons.push("Price above VWAP");
    score += 5;
  }
  if (closes[i] < vw[i] && action === "SELL") {
    reasons.push("Price below VWAP");
    score += 5;
  }

  const atrVal = last(atr14) ?? (highs[i] - lows[i]);
  const symbol = candles[i].symbol;

  const features = extractMlFeatures(candles, 1);

  if (action === "NO_TRADE") {
    return { suggestion: null, ruleScore: Math.min(100, score), features };
  }

  const entry = closes[i];
  const stopDist = Math.max(atrVal * 1.5, entry * 0.004);
  const stopLoss = action === "BUY" ? entry - stopDist : entry + stopDist;
  const target = action === "BUY" ? entry + stopDist * 1.6 : entry - stopDist * 1.6;

  return {
    suggestion: {
      symbol,
      action,
      entry: Math.round(entry * 100) / 100,
      stopLoss: Math.round(stopLoss * 100) / 100,
      target: Math.round(target * 100) / 100,
      reason: reasons.filter(Boolean),
      timeframe: "1m",
    },
    ruleScore: Math.min(100, score),
    features,
  };
}
