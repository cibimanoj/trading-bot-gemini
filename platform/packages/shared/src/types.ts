export type Side = "BUY" | "SELL" | "NO_TRADE";

/** Market regime for strategy routing */
export type MarketRegime =
  | "TRENDING_UP"
  | "TRENDING_DOWN"
  | "SIDEWAYS"
  | "HIGH_VOLATILITY"
  | "LOW_VOLATILITY";

export interface RegimeState {
  regime: MarketRegime;
  confidence: number;
  /** Normalized hints for logging / ML (trend strength, atr%, bb width, etc.) */
  features: number[];
}

export type StrategyId = "trend_ema" | "mean_reversion_vwap" | "volatility_breakout";

export interface Candle {
  symbol: string;
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Tick {
  symbol: string;
  ts: number;
  ltp: number;
  volume?: number;
}

export interface MarketDataEnvelope {
  type: "tick" | "ohlc" | "snapshot";
  symbol: string;
  payload: Tick | Candle | Candle[];
  source: string;
  receivedAt: number;
}

export interface TradeSuggestion {
  symbol: string;
  action: Side;
  entry: number;
  stopLoss: number;
  target: number;
  confidence: number;
  reason: string[];
  timeframe?: string;
  generatedAt: number;
  ruleScore?: number;
  mlScore?: number;
  mlLabel?: Side;
  /** Orchestration: regime at signal time */
  regime?: MarketRegime;
  regimeConfidence?: number;
  /** Which strategy produced the base signal */
  strategyId?: StrategyId;
  /** Multi-factor confirmation (0–100) */
  confirmationScore?: number;
  confirmationFactors?: string[];
  /** Position sizing multiplier from vol + confidence (e.g. 0.5–1.25) */
  allocationMultiplier?: number;
}

/** Internal candidate before orchestration merges ML and confirmation */
export interface StrategyCandidate {
  strategyId: StrategyId;
  suggestion: Omit<
    TradeSuggestion,
    | "generatedAt"
    | "confidence"
    | "regime"
    | "regimeConfidence"
    | "confirmationScore"
    | "confirmationFactors"
    | "allocationMultiplier"
  >;
  ruleScore: number;
  features: number[];
}

export interface OptionStrikeRow {
  strike: number;
  ceOi?: number;
  peOi?: number;
  ceLtp?: number;
  peLtp?: number;
}

export interface OptionsIntelligencePayload {
  symbol: string;
  expiry?: string;
  pcr: number;
  totalCeOi: number;
  totalPeOi: number;
  supportZones: number[];
  resistanceZones: number[];
  oiBuildupNotes: string[];
  computedAt: number;
}

export interface RiskAssessment {
  approved: boolean;
  rejectReasons: string[];
  positionSizeUnits: number;
  riskRewardRatio: number;
  maxLossAmount: number;
  dailyPnlImpact: number;
  /** Effective risk % after allocation multiplier */
  effectiveRiskPct?: number;
}

export interface ValidatedSignalEvent {
  suggestion: TradeSuggestion;
  risk: RiskAssessment;
  validatedAt: number;
}
