import pRetry from "p-retry";
import type { OptionStrikeRow, OptionsIntelligencePayload } from "@ta/shared";

export interface RawChainResponse {
  strikes: Array<{
    strike: number;
    ce?: { oi?: number; ltp?: number };
    pe?: { oi?: number; ltp?: number };
  }>;
}

export async function fetchOptionChain(
  baseUrl: string | undefined,
  token: string | undefined,
  symbol: string,
): Promise<OptionStrikeRow[]> {
  if (!baseUrl) return syntheticChain(symbol);

  const url = `${baseUrl.replace(/\/$/, "")}/market/v1/option-chain?symbol=${encodeURIComponent(symbol)}`;
  const res = await pRetry(
    async () => {
      const r = await fetch(url, {
        headers: {
          "content-type": "application/json",
          ...(token ? { authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!r.ok) throw new Error(`option-chain ${r.status}`);
      return r.json() as Promise<RawChainResponse>;
    },
    { retries: 3, factor: 2 },
  );

  return (res.strikes ?? []).map((s) => ({
    strike: s.strike,
    ceOi: s.ce?.oi,
    peOi: s.pe?.oi,
    ceLtp: s.ce?.ltp,
    peLtp: s.pe?.ltp,
  }));
}

function syntheticChain(symbol: string): OptionStrikeRow[] {
  const base = (symbol.length * 97) % 400 + 21_800;
  const rows: OptionStrikeRow[] = [];
  for (let i = -8; i <= 8; i++) {
    const strike = base + i * 50;
    rows.push({
      strike,
      ceOi: 5000 + i * 200 + (Date.now() % 1000),
      peOi: 4800 - i * 180 + (Date.now() % 900),
      ceLtp: Math.max(1, 80 - Math.abs(i) * 4),
      peLtp: Math.max(1, 75 - Math.abs(i) * 3),
    });
  }
  return rows;
}

export function analyzeChain(
  symbol: string,
  rows: OptionStrikeRow[],
): OptionsIntelligencePayload {
  let totalCe = 0;
  let totalPe = 0;
  const oiByStrike: { strike: number; net: number }[] = [];

  for (const r of rows) {
    const ce = r.ceOi ?? 0;
    const pe = r.peOi ?? 0;
    totalCe += ce;
    totalPe += pe;
    oiByStrike.push({ strike: r.strike, net: pe - ce });
  }

  const pcr = totalCe > 0 ? totalPe / totalCe : 1;

  const sorted = [...oiByStrike].sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
  const supportZones = sorted.filter((x) => x.net > 0).slice(0, 2).map((x) => x.strike);
  const resistanceZones = sorted.filter((x) => x.net < 0).slice(0, 2).map((x) => x.strike);

  const oiBuildupNotes: string[] = [];
  if (pcr > 1.2) oiBuildupNotes.push("Elevated PCR — put-heavy positioning");
  if (pcr < 0.85) oiBuildupNotes.push("Low PCR — call-heavy positioning");
  if (supportZones.length) {
    oiBuildupNotes.push(`Potential support near ${supportZones.join(", ")}`);
  }
  if (resistanceZones.length) {
    oiBuildupNotes.push(`OI resistance pockets near ${resistanceZones.join(", ")}`);
  }

  return {
    symbol,
    pcr: Math.round(pcr * 1000) / 1000,
    totalCeOi: totalCe,
    totalPeOi: totalPe,
    supportZones,
    resistanceZones,
    oiBuildupNotes,
    computedAt: Date.now(),
  };
}
