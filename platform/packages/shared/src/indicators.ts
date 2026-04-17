/**
 * Technical indicators on ascending time-ordered OHLCV arrays.
 * Pure functions — no I/O.
 */

/** Exponential moving average; seeds with first close (stable for crossovers). */
export function ema(values: number[], period: number): number[] {
  if (period <= 0 || values.length === 0) return [];
  const k = 2 / (period + 1);
  const out: number[] = [];
  let prev = values[0];
  out.push(prev);
  for (let i = 1; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

export function rsi(closes: number[], period = 14): number[] {
  if (closes.length < period + 1) return closes.map(() => 50);
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    const ch = closes[i] - closes[i - 1];
    gains.push(ch > 0 ? ch : 0);
    losses.push(ch < 0 ? -ch : 0);
  }
  const out: number[] = new Array(closes.length).fill(50);
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 0; i < period; i++) {
    avgGain += gains[i];
    avgLoss += losses[i];
  }
  avgGain /= period;
  avgLoss /= period;
  const rs0 = avgLoss === 0 ? 100 : avgGain / avgLoss;
  out[period] = 100 - 100 / (1 + rs0);

  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    out[i + 1] = 100 - 100 / (1 + rs);
  }
  return out;
}

export function vwap(
  highs: number[],
  lows: number[],
  closes: number[],
  volumes: number[],
): number[] {
  const n = closes.length;
  const out: number[] = new Array(n).fill(0);
  let cumPv = 0;
  let cumV = 0;
  for (let i = 0; i < n; i++) {
    const typical = (highs[i] + lows[i] + closes[i]) / 3;
    const v = volumes[i] || 0;
    cumPv += typical * v;
    cumV += v;
    out[i] = cumV === 0 ? typical : cumPv / cumV;
  }
  return out;
}

export function atr(
  highs: number[],
  lows: number[],
  closes: number[],
  period = 14,
): number[] {
  const n = closes.length;
  const tr: number[] = [];
  tr.push(highs[0] - lows[0]);
  for (let i = 1; i < n; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    tr.push(Math.max(hl, hc, lc));
  }
  const out: number[] = new Array(n).fill(0);
  if (n < period) return out;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += tr[i];
  out[period - 1] = sum / period;
  for (let i = period; i < n; i++) {
    out[i] = (out[i - 1] * (period - 1) + tr[i]) / period;
  }
  return out;
}

export function volumeSma(volumes: number[], period: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < volumes.length; i++) {
    const start = Math.max(0, i - period + 1);
    const slice = volumes.slice(start, i + 1);
    out.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  return out;
}

/** Standard deviation of last `period` closes ending at index i */
function rollingStdStdDev(closes: number[], i: number, period: number): number {
  if (i < period - 1) return 0;
  const start = i - period + 1;
  let sum = 0;
  for (let j = start; j <= i; j++) sum += closes[j];
  const mean = sum / period;
  let v = 0;
  for (let j = start; j <= i; j++) {
    const d = closes[j] - mean;
    v += d * d;
  }
  return Math.sqrt(v / period);
}

/** Bollinger bands (SMA basis + k * stdev). Returns aligned arrays. */
export function bollingerBands(
  closes: number[],
  period = 20,
  k = 2,
): { upper: number[]; middle: number[]; lower: number[]; width: number[] } {
  const n = closes.length;
  const upper: number[] = new Array(n).fill(0);
  const middle: number[] = new Array(n).fill(0);
  const lower: number[] = new Array(n).fill(0);
  const width: number[] = new Array(n).fill(0);
  const sma = (end: number): number => {
    let s = 0;
    for (let j = end - period + 1; j <= end; j++) s += closes[j];
    return s / period;
  };
  for (let i = 0; i < n; i++) {
    if (i < period - 1) continue;
    const mid = sma(i);
    const sd = rollingStdStdDev(closes, i, period);
    const u = mid + k * sd;
    const l = mid - k * sd;
    middle[i] = mid;
    upper[i] = u;
    lower[i] = l;
    width[i] = mid !== 0 ? (u - l) / mid : 0;
  }
  return { upper, middle, lower, width };
}
