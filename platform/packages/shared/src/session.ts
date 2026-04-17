/**
 * India session helpers (IST). Used for time-of-day gating without requiring host TZ.
 */

function istHourMinute(ts: number): { hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(ts));
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  return { hour, minute };
}

/** Minutes from 00:00 IST (same day as `ts`). */
export function istMinutesOfDay(ts: number): number {
  const { hour, minute } = istHourMinute(ts);
  return hour * 60 + minute;
}

export interface SessionGateConfig {
  /** First tradable minute IST (default 9:20 = 9*60+20, after open auction) */
  sessionStartMinutes: number;
  /** Last tradable minute IST (default 14:30) */
  sessionEndMinutes: number;
  /** Skip first N minutes after sessionStart (default 5 → first window 9:25 if start 9:20) */
  skipOpenMinutes: number;
  /** Weekly expiry (Thu): allow past normal end if true */
  isExpiryDay: boolean;
  /** When expiry day, extend end to this minute IST (default 15:25) */
  expirySessionEndMinutes: number;
}

const DEFAULTS: SessionGateConfig = {
  sessionStartMinutes: 9 * 60 + 15,
  sessionEndMinutes: 14 * 60 + 30,
  skipOpenMinutes: 5,
  isExpiryDay: false,
  expirySessionEndMinutes: 15 * 60 + 25,
};

export function isSignalSessionAllowed(
  candleTs: number,
  cfg: Partial<SessionGateConfig> = {},
): { ok: boolean; reason?: string } {
  const c = { ...DEFAULTS, ...cfg };
  const m = istMinutesOfDay(candleTs);
  const openSkipEnd = c.sessionStartMinutes + c.skipOpenMinutes;
  const end = c.isExpiryDay ? Math.max(c.sessionEndMinutes, c.expirySessionEndMinutes) : c.sessionEndMinutes;

  if (m < openSkipEnd) {
    return { ok: false, reason: "Skip first minutes after open (IST)" };
  }
  if (m > end) {
    return { ok: false, reason: c.isExpiryDay ? "After expiry session window (IST)" : "After cut-off (IST)" };
  }
  return { ok: true };
}

/** Morning vs midday vs close — for strategy hints / logging */
export type IntradayBucket = "OPEN_DRIVE" | "MID_SESSION" | "LATE";

export function intradayBucket(ts: number): IntradayBucket {
  const m = istMinutesOfDay(ts);
  if (m < 11 * 60 + 30) return "OPEN_DRIVE";
  if (m < 14 * 60) return "MID_SESSION";
  return "LATE";
}
