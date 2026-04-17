/**
 * Backtest harness: runs rule engine on synthetic OHLC series.
 * Wire CSV / DB loaders here for historical replay.
 */

import { type Candle, evaluateRules } from "@ta/shared";

function synthSeries(symbol: string, n: number): Candle[] {
  const out: Candle[] = [];
  let last = 100;
  const t0 = Date.now() - n * 60_000;
  for (let i = 0; i < n; i++) {
    const o = last;
    const c = o + (Math.sin(i / 8) * 0.4 + (Math.random() - 0.5) * 0.2);
    const h = Math.max(o, c) + Math.random() * 0.15;
    const l = Math.min(o, c) - Math.random() * 0.15;
    const v = 8000 + Math.floor(Math.random() * 2000);
    out.push({
      symbol,
      ts: t0 + i * 60_000,
      open: o,
      high: h,
      low: l,
      close: c,
      volume: v,
    });
    last = c;
  }
  return out;
}

function main(): void {
  const candles = synthSeries("NIFTY", 200);
  const { suggestion, ruleScore } = evaluateRules({ candles });
  let wins = 0;
  let losses = 0;
  let peak = 0;
  let equity = 0;
  let maxDd = 0;

  for (let i = 60; i < candles.length; i++) {
    const slice = candles.slice(0, i + 1);
    const ev = evaluateRules({ candles: slice });
    if (!ev.suggestion || ev.suggestion.action === "NO_TRADE") continue;
    const next = candles[i + 1];
    if (!next) break;
    const dir = ev.suggestion.action === "BUY" ? 1 : -1;
    const ret = dir * (next.close - ev.suggestion.entry);
    if (ret > 0) wins += 1;
    else losses += 1;
    equity += ret;
    peak = Math.max(peak, equity);
    maxDd = Math.max(maxDd, peak - equity);
  }

  const total = wins + losses;
  const winRate = total ? wins / total : 0;
  const profitFactor = losses === 0 ? wins : wins / Math.max(1, losses);

  console.log(
    JSON.stringify(
      {
        sampleSuggestion: suggestion,
        ruleScore,
        winRate: Math.round(winRate * 1000) / 10,
        maxDrawdown: Math.round(maxDd * 100) / 100,
        profitFactor: Math.round(profitFactor * 100) / 100,
        trades: total,
      },
      null,
      2,
    ),
  );
}

main();
