import { Kafka, logLevel } from "kafkajs";
import { Redis } from "ioredis";
import {
  KAFKA_TOPICS,
  REDIS_CHANNELS,
  type TradeSuggestion,
  type ValidatedSignalEvent,
} from "@ta/shared";
import { loadEnv } from "./env.js";
import { validateTrade, type RiskState } from "./risk.js";

const env = loadEnv();
const kafka = new Kafka({
  clientId: "risk-engine",
  brokers: env.KAFKA_BROKERS.split(",").map((b) => b.trim()),
  logLevel: logLevel.NOTHING,
});

function dayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

const REDIS_KEYS = {
  consecutiveLosses: "risk:consecutive_losses",
  openPositions: "risk:open_positions",
  killSwitch: "risk:kill_switch",
} as const;

async function readRiskOverlay(redis: Redis): Promise<{
  consecutiveLosses: number;
  openPositions: number;
  killSwitch: boolean;
}> {
  try {
    const [cl, op, ks] = await redis.mget(
      REDIS_KEYS.consecutiveLosses,
      REDIS_KEYS.openPositions,
      REDIS_KEYS.killSwitch,
    );
    return {
      consecutiveLosses: Number(cl ?? 0) || 0,
      openPositions: Number(op ?? 0) || 0,
      killSwitch: ks === "1" || ks === "true" || env.RISK_KILL_SWITCH,
    };
  } catch {
    return {
      consecutiveLosses: 0,
      openPositions: 0,
      killSwitch: env.RISK_KILL_SWITCH,
    };
  }
}

async function main(): Promise<void> {
  const redis = new Redis(env.REDIS_URL);
  const consumer = kafka.consumer({ groupId: env.GROUP_ID });
  await consumer.connect();
  await consumer.subscribe({ topic: KAFKA_TOPICS.SIGNALS_GENERATED, fromBeginning: false });

  let state: RiskState = { dayKey: dayKey(), realizedPnl: 0, approvedSignalsToday: 0 };

  await consumer.run({
    eachMessage: async ({ message }) => {
      if (!message.value) return;
      let suggestion: TradeSuggestion;
      try {
        suggestion = JSON.parse(message.value.toString()) as TradeSuggestion;
      } catch {
        return;
      }

      const dk = dayKey();
      if (state.dayKey !== dk) {
        state = { dayKey: dk, realizedPnl: 0, approvedSignalsToday: 0 };
      }

      const overlay = await readRiskOverlay(redis);

      const risk = validateTrade(
        suggestion,
        env.ACCOUNT_EQUITY,
        env.RISK_PCT,
        env.MIN_RR,
        env.DAILY_LOSS_LIMIT_PCT,
        state,
        {
          allocationMultiplier: suggestion.allocationMultiplier,
          minConfirmationScore: env.MIN_CONFIRMATION_SCORE,
          maxOpenPositions: env.MAX_OPEN_POSITIONS,
          currentOpenPositions: overlay.openPositions,
          maxConsecutiveLosses: env.MAX_CONSECUTIVE_LOSSES,
          consecutiveLosses: overlay.consecutiveLosses,
          killSwitch: overlay.killSwitch,
          maxDailyApprovedSignals: env.MAX_DAILY_APPROVED_SIGNALS,
        },
      );

      if (risk.approved) {
        state = { ...state, approvedSignalsToday: state.approvedSignalsToday + 1 };
      }

      const evt: ValidatedSignalEvent = {
        suggestion,
        risk,
        validatedAt: Date.now(),
      };

      await redis.publish(REDIS_CHANNELS.SIGNALS, JSON.stringify(evt));

      if (!risk.approved) {
        await redis.publish(
          REDIS_CHANNELS.ALERTS,
          JSON.stringify({
            level: "warn",
            message: `Signal rejected: ${suggestion.symbol}`,
            reasons: risk.rejectReasons,
            at: Date.now(),
          }),
        );
      }
    },
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
