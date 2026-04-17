import type { RiskAssessment, TradeSuggestion } from "@ta/shared";

export interface RiskState {
  dayKey: string;
  realizedPnl: number;
  /** Signals approved today (increment externally or via risk consumer) */
  approvedSignalsToday: number;
}

export interface RiskValidateOptions {
  /** From orchestrator: scales effective risk % */
  allocationMultiplier?: number;
  /** Reject if confirmation layer weaker than this */
  minConfirmationScore?: number;
  maxOpenPositions: number;
  /** Current open positions (set via Redis or execution feedback) */
  currentOpenPositions: number;
  maxConsecutiveLosses: number;
  consecutiveLosses: number;
  killSwitch: boolean;
  maxDailyApprovedSignals: number;
}

export function validateTrade(
  s: TradeSuggestion,
  equity: number,
  riskPct: number,
  minRr: number,
  dailyLossLimitPct: number,
  state: RiskState,
  opts: RiskValidateOptions,
): RiskAssessment {
  const rejectReasons: string[] = [];

  if (opts.killSwitch) {
    rejectReasons.push("Kill switch active");
  }

  if (opts.consecutiveLosses >= opts.maxConsecutiveLosses) {
    rejectReasons.push(
      `Paused: consecutive losses ${opts.consecutiveLosses} ≥ ${opts.maxConsecutiveLosses}`,
    );
  }

  if (opts.currentOpenPositions >= opts.maxOpenPositions) {
    rejectReasons.push(
      `Max open positions ${opts.currentOpenPositions}/${opts.maxOpenPositions}`,
    );
  }

  if (state.approvedSignalsToday >= opts.maxDailyApprovedSignals) {
    rejectReasons.push(`Daily signal cap ${opts.maxDailyApprovedSignals} reached`);
  }

  const minConf = opts.minConfirmationScore ?? 0;
  if (minConf > 0 && (s.confirmationScore ?? 0) < minConf) {
    rejectReasons.push(
      `Confirmation ${s.confirmationScore ?? 0} below minimum ${minConf}`,
    );
  }

  const riskPerShare = Math.abs(s.entry - s.stopLoss);
  const rewardPerShare = Math.abs(s.target - s.entry);
  const rr = riskPerShare > 0 ? rewardPerShare / riskPerShare : 0;
  if (rr < minRr) {
    rejectReasons.push(`Risk/Reward ${rr.toFixed(2)} below minimum ${minRr}`);
  }

  const alloc = Math.min(1.25, Math.max(0.4, s.allocationMultiplier ?? 1));
  const effectiveRiskPct = riskPct * alloc;

  const maxLossAmount = equity * effectiveRiskPct;
  let positionSizeUnits = riskPerShare > 0 ? maxLossAmount / riskPerShare : 0;

  const maxUnitsByMargin = s.entry > 0 ? equity / s.entry : 0;
  if (positionSizeUnits > maxUnitsByMargin) {
    positionSizeUnits = maxUnitsByMargin;
  }
  if (positionSizeUnits <= 0) {
    rejectReasons.push("Invalid stop distance for position sizing");
  }

  const dailyLimit = -Math.abs(equity * dailyLossLimitPct);
  const dailyPnlImpact = state.realizedPnl - maxLossAmount * 0.1;
  if (state.realizedPnl <= dailyLimit) {
    rejectReasons.push("Daily loss limit reached");
  }

  const approved = rejectReasons.length === 0;
  return {
    approved,
    rejectReasons,
    positionSizeUnits: Math.floor(positionSizeUnits),
    riskRewardRatio: Math.round(rr * 100) / 100,
    maxLossAmount,
    dailyPnlImpact,
    effectiveRiskPct,
  };
}
