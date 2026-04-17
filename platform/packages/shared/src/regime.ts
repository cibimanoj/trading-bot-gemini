import { atr, bollingerBands, ema } from "./indicators.js";
import type { Candle, MarketRegime, RegimeState } from "./types.js";

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

/**
 * Classify regime from OHLC: trend vs chop vs vol expansion vs squeeze.
 * Needs ~60+ bars for stable BB width history.
 */
export function detectRegime(candles: Candle[]): RegimeState {
  const minBars = 60;
  if (candles.length < minBars) {
    return {
      regime: "SIDEWAYS",
      confidence: 35,
      features: [0, 0, 0, 0, 0],
    };
  }

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const i = closes.length - 1;

  const e21 = ema(closes, 21);
  const e50 = ema(closes, 50);
  const atr14 = atr(highs, lows, closes, 14);
  const { width } = bollingerBands(closes, 20, 2);

  const atrVal = last(atr14) ?? highs[i] - lows[i];
  const atrPct = closes[i] !== 0 ? atrVal / closes[i] : 0;

  const widths = width.slice(20, i + 1).filter((w) => w > 0);
  const wNow = width[i] || 0;
  const widthRank = widths.length ? percentileRank(widths, wNow) : 0.5;

  const trendSep = Math.abs(e21[i] - e50[i]) / (closes[i] || 1);
  const slope =
    i >= 5 ? (e21[i] - e21[i - 5]) / (closes[i] || 1) : 0;

  let regime: MarketRegime = "SIDEWAYS";
  let confidence = 50;

  if (atrPct > 0.018) {
    regime = "HIGH_VOLATILITY";
    confidence = Math.min(95, 55 + atrPct * 2000);
  } else if (widthRank < 0.2 && wNow > 0) {
    regime = "LOW_VOLATILITY";
    confidence = Math.min(90, 60 + (0.2 - widthRank) * 100);
  } else if (trendSep > 0.0025 && e21[i] > e50[i] && slope > 0) {
    regime = "TRENDING_UP";
    confidence = Math.min(92, 52 + trendSep * 8000 + Math.max(0, slope) * 2000);
  } else if (trendSep > 0.0025 && e21[i] < e50[i] && slope < 0) {
    regime = "TRENDING_DOWN";
    confidence = Math.min(92, 52 + trendSep * 8000 + Math.max(0, -slope) * 2000);
  } else {
    regime = "SIDEWAYS";
    confidence = 45 + (1 - Math.min(1, trendSep * 500)) * 25;
  }

  const features = [trendSep, atrPct, widthRank, slope, e21[i] > e50[i] ? 1 : -1];

  return { regime, confidence: Math.round(confidence), features };
}
