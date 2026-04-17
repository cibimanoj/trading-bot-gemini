import { ema, rsi, volumeSma, vwap } from "./indicators.js";
import type { Candle, OptionsIntelligencePayload, StrategyCandidate } from "./types.js";

export interface ConfirmationResult {
  ok: boolean;
  score: number;
  factors: string[];
  factorCount: number;
}

/**
 * Multi-factor quorum: require `minFactors` independent confirmations before trading.
 */
export function confirmSignal(
  candidate: StrategyCandidate,
  candles: Candle[],
  optionsIntel: OptionsIntelligencePayload | null,
  minFactors: number,
): ConfirmationResult {
  const factors: string[] = [];
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const vols = candles.map((c) => c.volume);
  const i = closes.length - 1;
  const action = candidate.suggestion.action;

  if (candles.length < 30) {
    return { ok: false, score: 0, factors: ["Insufficient bars"], factorCount: 0 };
  }

  const rsi14 = rsi(closes, 14);
  const vw = vwap(highs, lows, closes, vols);
  const e21 = ema(closes, 21);
  const e50 = ema(closes, 50);
  const volSma20 = volumeSma(vols, 20);

  // 1) Price action / structure
  if (action === "BUY" && closes[i] > e21[i] && closes[i] >= closes[i - 1]) {
    factors.push("Price action: higher close vs prior / above short EMA");
  } else if (action === "SELL" && closes[i] < e21[i] && closes[i] <= closes[i - 1]) {
    factors.push("Price action: lower close vs prior / below short EMA");
  }

  // 2) Volume
  if (volSma20[i] > 0 && vols[i] > volSma20[i] * 1.15) {
    factors.push("Volume spike vs 20-bar avg");
  }

  // 3) Indicator alignment (EMA trend)
  if (action === "BUY" && e21[i] > e50[i]) {
    factors.push("EMA alignment (21>50)");
  }
  if (action === "SELL" && e21[i] < e50[i]) {
    factors.push("EMA alignment (21<50)");
  }

  // 4) VWAP
  if (action === "BUY" && closes[i] > vw[i]) {
    factors.push("Close above VWAP");
  }
  if (action === "SELL" && closes[i] < vw[i]) {
    factors.push("Close below VWAP");
  }

  // 5) RSI not at exhaustion for direction
  const rv = rsi14[i];
  if (action === "BUY" && rv > 42 && rv < 72) {
    factors.push("RSI supports long");
  }
  if (action === "SELL" && rv < 58 && rv > 28) {
    factors.push("RSI supports short");
  }

  // 6) Options context
  if (optionsIntel && optionsIntel.symbol === candidate.suggestion.symbol) {
    const pcr = optionsIntel.pcr;
    if (action === "BUY" && pcr < 1.05) {
      factors.push("Options: PCR not put-heavy");
    }
    if (action === "SELL" && pcr > 0.95) {
      factors.push("Options: PCR not call-heavy");
    }
    if (optionsIntel.oiBuildupNotes.length > 0) {
      factors.push("Options: OI context available");
    }
  }

  const factorCount = factors.length;
  const score = Math.min(100, 35 + factorCount * 14);
  const ok = factorCount >= minFactors;

  return { ok, score, factors, factorCount };
}
