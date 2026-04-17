/** Kafka topic names — single source of truth */
export const KAFKA_TOPICS = {
  MARKET_DATA: "market-data",
  SIGNALS_GENERATED: "signals-generated",
  OPTIONS_INTELLIGENCE: "options-intelligence",
  RISK_EVENTS: "risk-events",
} as const;

export const REDIS_CHANNELS = {
  SIGNALS: "signals:validated",
  ALERTS: "alerts:broadcast",
  OPTIONS: "options:intelligence",
  LOGS: "logs:stream",
} as const;
