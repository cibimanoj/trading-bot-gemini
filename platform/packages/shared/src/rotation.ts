import type { StrategyId } from "./types.js";

/** Rolling counters for non-AI strategy rotation (pause losers, boost winners). */
export interface StrategyRotationCounters {
  wins: Partial<Record<StrategyId, number>>;
  losses: Partial<Record<StrategyId, number>>;
}

export function shouldPauseStrategy(losses: number, maxConsecutive = 3): boolean {
  return losses >= maxConsecutive;
}

export function allocationBoost(wins: number, losses: number): number {
  const net = wins - losses;
  if (net >= 4) return 1.12;
  if (net <= -2) return 0.75;
  return 1;
}
