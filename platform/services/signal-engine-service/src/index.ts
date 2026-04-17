import { Kafka, logLevel } from "kafkajs";
import {
  KAFKA_TOPICS,
  orchestrateSignal,
  type Candle,
  type MarketDataEnvelope,
  type OptionsIntelligencePayload,
} from "@ta/shared";
import { loadEnv } from "./env.js";
import { predictSide, trainSignalForest } from "./ml.js";

const env = loadEnv();
const kafka = new Kafka({
  clientId: "signal-engine",
  brokers: env.KAFKA_BROKERS.split(",").map((b) => b.trim()),
  logLevel: logLevel.NOTHING,
});

const candleBuffer = new Map<string, Candle[]>();
const optionsIntelBySymbol = new Map<string, OptionsIntelligencePayload>();
const MAX = 200;

const model = trainSignalForest();

function pushCandles(symbol: string, candles: Candle[]): void {
  const cur = candleBuffer.get(symbol) ?? [];
  const merged = [...cur];
  for (const c of candles) {
    const idx = merged.findIndex((x) => x.ts === c.ts);
    if (idx >= 0) merged[idx] = c;
    else merged.push(c);
  }
  merged.sort((a, b) => a.ts - b.ts);
  candleBuffer.set(symbol, merged.slice(-MAX));
}

async function main(): Promise<void> {
  const consumer = kafka.consumer({ groupId: env.GROUP_ID });
  const producer = kafka.producer();
  await consumer.connect();
  await producer.connect();

  await consumer.subscribe({
    topics: [KAFKA_TOPICS.MARKET_DATA, KAFKA_TOPICS.OPTIONS_INTELLIGENCE],
    fromBeginning: false,
  });

  await consumer.run({
    eachMessage: async ({ message, topic }) => {
      if (!message.value) return;

      if (topic === KAFKA_TOPICS.OPTIONS_INTELLIGENCE) {
        try {
          const intel = JSON.parse(message.value.toString()) as OptionsIntelligencePayload;
          if (intel.symbol) optionsIntelBySymbol.set(intel.symbol, intel);
        } catch {
          return;
        }
        return;
      }

      let envelope: MarketDataEnvelope;
      try {
        envelope = JSON.parse(message.value.toString()) as MarketDataEnvelope;
      } catch {
        return;
      }

      if (envelope.type === "ohlc" && Array.isArray(envelope.payload)) {
        pushCandles(envelope.symbol, envelope.payload as Candle[]);
      } else {
        return;
      }

      const candles = candleBuffer.get(envelope.symbol);
      if (!candles || candles.length < 60) return;

      const optionsIntel = optionsIntelBySymbol.get(envelope.symbol) ?? null;

      const { suggestion, sessionBlocked } = orchestrateSignal(
        candles,
        optionsIntel,
        (features) => predictSide(model, features),
        {
          minConfirmationFactors: env.MIN_CONFIRMATION_FACTORS,
          minCombinedConfidence: env.MIN_COMBINED_CONFIDENCE,
          mlOnlyMinConfidence: env.ML_ONLY_MIN_CONFIDENCE,
          session: { isExpiryDay: env.IS_EXPIRY_DAY },
        },
      );

      if (sessionBlocked || !suggestion) return;

      await producer.send({
        topic: KAFKA_TOPICS.SIGNALS_GENERATED,
        messages: [{ key: suggestion.symbol, value: JSON.stringify(suggestion) }],
      });
    },
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
