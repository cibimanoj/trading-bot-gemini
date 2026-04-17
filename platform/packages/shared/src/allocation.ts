import { atr } from "./indicators.js";
import type { Candle } from "./types.js";
import type { MarketRegime } from "./types.js";

function last<T>(arr: T[]): T | undefined {
  return arr[arr.length - 1];
}

export interface AllocationInput {
  candles: Candle[];
  regime: MarketRegime;
  /** 0–100 combined confidence */
  confidence: number;
}

/**
 * Scale size down in high vol / low confidence; slight boost when calm + confident.
 * Returns multiplier applied to base risk (e.g. 0.5–1.25).
 */
export function computeAllocationMultiplier(input: AllocationInput): number {
  const { candles, regime, confidence } = input;
  if (candles.length < 20) return 0.65;

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const closes = candles.map((c) => c.close);
  const atr14 = atr(highs, lows, closes, 14);
  const i = closes.length - 1;
  const atrVal = last(atr14) ?? highs[i] - lows[i];
  const atrPct = closes[i] !== 0 ? atrVal / closes[i] : 0;

  let m = 1;

  if (regime === "HIGH_VOLATILITY" || atrPct > 0.016) {
    m *= 0.65;
  } else if (regime === "LOW_VOLATILITY") {
    m *= 1.08;
  }

  if (confidence >= 72) m *= 1.1;
  else if (confidence < 48) m *= 0.75;

  return Math.min(1.25, Math.max(0.45, Math.round(m * 1000) / 1000));
}
