/**
 * Groww (or compatible) read-only market data adapter.
 * Configure GROWW_API_BASE_URL to your broker HTTP gateway; no order endpoints are called.
 */

import pRetry from "p-retry";
import CircuitBreaker from "opossum";
import type { Candle, Tick } from "@ta/shared";

export interface GrowwQuoteResponse {
  symbol: string;
  ltp: number;
  ts?: number;
  volume?: number;
}

export interface GrowwOhlcBar {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export class GrowwMarketDataAdapter {
  constructor(
    private readonly baseUrl: string | undefined,
    private readonly accessToken: string | undefined,
  ) {}

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "content-type": "application/json" };
    if (this.accessToken) h.authorization = `Bearer ${this.accessToken}`;
    return h;
  }

  /** Fetch last traded price / tick — retries with backoff when HTTP fails */
  async fetchTick(symbol: string): Promise<Tick> {
    if (!this.baseUrl) {
      return syntheticTick(symbol);
    }
    const url = `${this.baseUrl.replace(/\/$/, "")}/market/v1/quote/${encodeURIComponent(symbol)}`;
    const res = await pRetry(
      async () => {
        const r = await fetch(url, { headers: this.headers() });
        if (!r.ok) throw new Error(`quote ${r.status}`);
        return r.json() as Promise<GrowwQuoteResponse>;
      },
      { retries: 4, factor: 2, minTimeout: 500 },
    );
    return {
      symbol: res.symbol,
      ltp: res.ltp,
      ts: res.ts ?? Date.now(),
      volume: res.volume,
    };
  }

  /** Historical / intraday OHLC — shape may differ; normalize in caller */
  async fetchOhlc(symbol: string, interval: string): Promise<Candle[]> {
    if (!this.baseUrl) {
      return syntheticOhlc(symbol);
    }
    const url = `${this.baseUrl.replace(/\/$/, "")}/market/v1/ohlc?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`;
    const res = await pRetry(
      async () => {
        const r = await fetch(url, { headers: this.headers() });
        if (!r.ok) throw new Error(`ohlc ${r.status}`);
        return r.json() as Promise<{ bars: GrowwOhlcBar[] }>;
      },
      { retries: 3, factor: 2, minTimeout: 800 },
    );
    return (res.bars ?? []).map((b) => ({
      symbol,
      ts: b.ts,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
    }));
  }

  createQuoteBreaker(): CircuitBreaker<[string], Tick> {
    return new CircuitBreaker(
      async (symbol: string) => this.fetchTick(symbol),
      {
        timeout: 8000,
        errorThresholdPercentage: 50,
        resetTimeout: 30_000,
        volumeThreshold: 5,
      },
    );
  }
}

/** Deterministic synthetic data when no API URL is set (local dev / circuit fallback). */
export function syntheticTick(symbol: string): Tick {
  const base = hashSymbol(symbol) % 5000 + 18000;
  const wobble = Math.sin(Date.now() / 5000) * 15;
  return {
    symbol,
    ltp: Math.round((base + wobble) * 100) / 100,
    ts: Date.now(),
    volume: 1000 + (Date.now() % 5000),
  };
}

function syntheticOhlc(symbol: string): Candle[] {
  const out: Candle[] = [];
  let last = hashSymbol(symbol) % 200 + 100;
  const now = Date.now();
  for (let i = 59; i >= 0; i--) {
    const ts = now - i * 60_000;
    const o = last;
    const c = o + (Math.random() - 0.45) * 2;
    const h = Math.max(o, c) + Math.random();
    const l = Math.min(o, c) - Math.random();
    const v = 5000 + Math.floor(Math.random() * 2000);
    out.push({ symbol, ts, open: o, high: h, low: l, close: c, volume: v });
    last = c;
  }
  return out;
}

function hashSymbol(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}
