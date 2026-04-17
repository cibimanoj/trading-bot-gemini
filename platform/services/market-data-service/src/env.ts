import { z } from "zod";

const schema = z.object({
  PORT: z.coerce.number().default(3001),
  KAFKA_BROKERS: z.string().default("localhost:9092"),
  GROWW_API_BASE_URL: z
    .preprocess((v) => (v === "" || v == null ? undefined : v), z.string().url().optional()),
  GROWW_ACCESS_TOKEN: z.string().optional(),
  SYMBOLS: z.string().default("NIFTY,BANKNIFTY"),
  POLL_MS: z.coerce.number().default(2000),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const parsed = schema.safeParse(process.env);
  if (!parsed.success) {
    console.error(parsed.error.flatten());
    throw new Error("Invalid environment for market-data-service");
  }
  return parsed.data;
}
