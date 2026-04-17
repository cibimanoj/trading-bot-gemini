import { z } from "zod";

const schema = z.object({
  PORT: z.coerce.number().default(3005),
  KAFKA_BROKERS: z.string().default("localhost:9092"),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  GROWW_API_BASE_URL: z
    .preprocess((v) => (v === "" || v == null ? undefined : v), z.string().url().optional()),
  GROWW_ACCESS_TOKEN: z.string().optional(),
  SYMBOLS: z.string().default("NIFTY"),
  POLL_MS: z.coerce.number().default(15_000),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const p = schema.safeParse(process.env);
  if (!p.success) throw new Error("Invalid env options-intelligence");
  return p.data;
}
