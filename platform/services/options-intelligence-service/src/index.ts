import { Kafka, logLevel } from "kafkajs";
import Fastify from "fastify";
import { Redis } from "ioredis";
import { KAFKA_TOPICS, REDIS_CHANNELS } from "@ta/shared";
import { loadEnv } from "./env.js";
import { analyzeChain, fetchOptionChain } from "./chain.js";

const env = loadEnv();
const symbols = env.SYMBOLS.split(",").map((s) => s.trim()).filter(Boolean);

const kafka = new Kafka({
  clientId: "options-intelligence",
  brokers: env.KAFKA_BROKERS.split(",").map((b) => b.trim()),
  logLevel: logLevel.NOTHING,
});

async function main(): Promise<void> {
  const producer = kafka.producer();
  await producer.connect();
  const redis = new Redis(env.REDIS_URL);

  const app = Fastify({ logger: true });
  app.get("/health", async () => ({ ok: true, service: "options-intelligence" }));

  await app.listen({ port: env.PORT, host: "0.0.0.0" });

  async function cycle(): Promise<void> {
    for (const symbol of symbols) {
      try {
        const rows = await fetchOptionChain(
          env.GROWW_API_BASE_URL,
          env.GROWW_ACCESS_TOKEN,
          symbol,
        );
        const intel = analyzeChain(symbol, rows);
        await producer.send({
          topic: KAFKA_TOPICS.OPTIONS_INTELLIGENCE,
          messages: [{ key: symbol, value: JSON.stringify(intel) }],
        });
        await redis.publish(REDIS_CHANNELS.OPTIONS, JSON.stringify(intel));
      } catch (e) {
        app.log.error(e);
      }
    }
  }

  async function runCycle() {
    await cycle();
    setTimeout(() => { void runCycle(); }, env.POLL_MS);
  }

  void runCycle();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
