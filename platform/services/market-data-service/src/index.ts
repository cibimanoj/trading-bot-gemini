import { Kafka, logLevel, type Producer } from "kafkajs";
import Fastify from "fastify";
import { KAFKA_TOPICS, type MarketDataEnvelope } from "@ta/shared";
import { loadEnv } from "./env.js";
import { GrowwMarketDataAdapter, syntheticTick } from "./groww-adapter.js";

const env = loadEnv();
const symbols = env.SYMBOLS.split(",").map((s) => s.trim()).filter(Boolean);

const kafka = new Kafka({
  clientId: "market-data-service",
  brokers: env.KAFKA_BROKERS.split(",").map((b) => b.trim()),
  logLevel: logLevel.NOTHING,
});

let producer: Producer;

const adapter = new GrowwMarketDataAdapter(env.GROWW_API_BASE_URL, env.GROWW_ACCESS_TOKEN);
const breaker = adapter.createQuoteBreaker();

breaker.on("open", () => console.warn("[circuit] quote breaker OPEN — using synthetic ticks"));
breaker.on("halfOpen", () => console.warn("[circuit] quote breaker halfOpen"));
breaker.fallback((symbol: string) => syntheticTick(symbol));

async function publish(envelope: MarketDataEnvelope): Promise<void> {
  await producer.send({
    topic: KAFKA_TOPICS.MARKET_DATA,
    messages: [{ key: envelope.symbol, value: JSON.stringify(envelope) }],
  });
}

async function pollLoop(): Promise<void> {
  for (const symbol of symbols) {
    try {
      const tick = await breaker.fire(symbol);
      const envelope: MarketDataEnvelope = {
        type: "tick",
        symbol: tick.symbol,
        payload: tick,
        source: "groww-adapter",
        receivedAt: Date.now(),
      };
      await publish(envelope);
    } catch (e) {
      console.error(`[poll] ${symbol}`, e);
    }
  }
  try {
    for (const symbol of symbols) {
      const candles = await adapter.fetchOhlc(symbol, "1m");
      if (candles.length === 0) continue;
      const envelope: MarketDataEnvelope = {
        type: "ohlc",
        symbol,
        payload: candles,
        source: "groww-adapter",
        receivedAt: Date.now(),
      };
      await publish(envelope);
    }
  } catch (e) {
    console.error("[ohlc]", e);
  }
}

async function main(): Promise<void> {
  producer = kafka.producer();
  await producer.connect();

  const app = Fastify({ logger: true });
  app.get("/health", async () => ({ status: "ok", service: "market-data" }));

  await app.listen({ port: env.PORT, host: "0.0.0.0" });

  async function runLoop() {
    await pollLoop();
    setTimeout(() => { void runLoop(); }, env.POLL_MS);
  }

  void runLoop();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
