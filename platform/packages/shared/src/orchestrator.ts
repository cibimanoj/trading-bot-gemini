import { computeAllocationMultiplier } from "./allocation.js";
import { confirmSignal } from "./confirmation.js";
import { detectRegime } from "./regime.js";
import { pickBestCandidate, runStrategiesForRegime } from "./multiStrategy.js";
import { isSignalSessionAllowed, type SessionGateConfig } from "./session.js";
import { extractMlFeatures, evaluateRules } from "./strategy.js";
import type {
  Candle,
  OptionsIntelligencePayload,
  RegimeState,
  Side,
  StrategyCandidate,
  TradeSuggestion,
} from "./types.js";

export type MlPredictFn = (features: number[]) => { label: Side; score: number };

export interface OrchestrateConfig {
  minConfirmationFactors: number;
  /** Minimum combined confidence to emit a trade */
  minCombinedConfidence: number;
  /** ML-only path when no strategy fires */
  mlOnlyMinConfidence: number;
  session: Partial<SessionGateConfig>;
}

const DEFAULT_ORCH: OrchestrateConfig = {
  minConfirmationFactors: 3,
  minCombinedConfidence: 48,
  mlOnlyMinConfidence: 50,
  session: {},
};

function computeCombinedConfidence(
  ruleScore: number,
  confirmationScore: number,
  mlScore: number,
): number {
  return Math.min(
    100,
    Math.round(ruleScore * 0.28 + confirmationScore * 0.32 + mlScore * 0.4),
  );
}

export function orchestrateSignal(
  candles: Candle[],
  optionsIntel: OptionsIntelligencePayload | null,
  predictMl: MlPredictFn,
  cfg: Partial<OrchestrateConfig> = {},
): {
  suggestion: TradeSuggestion | null;
  regime: RegimeState;
  sessionBlocked?: string;
} {
  const config = { ...DEFAULT_ORCH, ...cfg, session: { ...DEFAULT_ORCH.session, ...cfg.session } };
  const last = candles[candles.length - 1];
  if (!last) {
    return {
      suggestion: null,
      regime: { regime: "SIDEWAYS", confidence: 0, features: [] },
    };
  }

  const sessionCheck = isSignalSessionAllowed(last.ts, config.session);
  if (!sessionCheck.ok) {
    return {
      suggestion: null,
      regime: detectRegime(candles),
      sessionBlocked: sessionCheck.reason,
    };
  }

  const pcr = optionsIntel?.pcr ?? 1;
  const regime = detectRegime(candles);
  const candidates = runStrategiesForRegime(regime.regime, candles);
  const best = pickBestCandidate(candidates);

  const features = extractMlFeatures(candles, pcr);
  const ml = predictMl(features);

  if (!best) {
    if (ml.label === "NO_TRADE") {
      return { suggestion: null, regime };
    }
    const flat = evaluateRules({ candles });
    const ruleScore = flat.ruleScore;
    const pseudo: StrategyCandidate = {
      strategyId: "trend_ema",
      suggestion: {
        symbol: last.symbol,
        action: ml.label,
        entry: last.close,
        stopLoss: ml.label === "BUY" ? last.close * 0.99 : last.close * 1.01,
        target: ml.label === "BUY" ? last.close * 1.01 : last.close * 0.99,
        reason: ["ML-only path (no regime strategy fired)", `Forest → ${ml.label}`],
        timeframe: "1m",
      },
      ruleScore,
      features,
    };
    const conf = confirmSignal(pseudo, candles, optionsIntel, config.minConfirmationFactors);
    if (!conf.ok) return { suggestion: null, regime };

    const confidence = computeCombinedConfidence(ruleScore, conf.score, ml.score);

    const alloc = computeAllocationMultiplier({
      candles,
      regime: regime.regime,
      confidence,
    });

    if (confidence < config.mlOnlyMinConfidence) {
      return { suggestion: null, regime };
    }

    return {
      suggestion: {
        ...pseudo.suggestion,
        confidence,
        generatedAt: Date.now(),
        ruleScore,
        mlScore: ml.score,
        mlLabel: ml.label,
        regime: regime.regime,
        regimeConfidence: regime.confidence,
        strategyId: "trend_ema",
        confirmationScore: conf.score,
        confirmationFactors: conf.factors,
        allocationMultiplier: alloc,
      },
      regime,
    };
  }

  const hybridAction: Side =
    ml.label !== "NO_TRADE" && ml.label !== best.suggestion.action ? "NO_TRADE" : best.suggestion.action;

  if (hybridAction === "NO_TRADE") {
    return { suggestion: null, regime };
  }

  const patched: StrategyCandidate = {
    ...best,
    features,
    suggestion: { ...best.suggestion, action: hybridAction },
  };

  const conf = confirmSignal(patched, candles, optionsIntel, config.minConfirmationFactors);
  if (!conf.ok) {
    return { suggestion: null, regime };
  }

  const confidence = computeCombinedConfidence(best.ruleScore, conf.score, ml.score);

  const alloc = computeAllocationMultiplier({
    candles,
    regime: regime.regime,
    confidence,
  });

  if (confidence < config.minCombinedConfidence) {
    return { suggestion: null, regime };
  }

  return {
    suggestion: {
      ...patched.suggestion,
      action: hybridAction,
      confidence,
      generatedAt: Date.now(),
      ruleScore: best.ruleScore,
      mlScore: ml.score,
      mlLabel: ml.label,
      regime: regime.regime,
      regimeConfidence: regime.confidence,
      strategyId: best.strategyId,
      confirmationScore: conf.score,
      confirmationFactors: conf.factors,
      allocationMultiplier: alloc,
    },
    regime,
  };
}
