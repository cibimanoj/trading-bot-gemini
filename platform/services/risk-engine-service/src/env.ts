import { z } from "zod";

const schema = z.object({
  KAFKA_BROKERS: z.string().default("localhost:9092"),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  GROUP_ID: z.string().default("risk-engine"),
  ACCOUNT_EQUITY: z.coerce.number().default(100_000),
  RISK_PCT: z.coerce.number().min(0.005).max(0.05).default(0.015),
  MIN_RR: z.coerce.number().default(1.5),
  DAILY_LOSS_LIMIT_PCT: z.coerce.number().default(0.03),
  MIN_CONFIRMATION_SCORE: z.coerce.number().min(0).max(100).default(0),
  MAX_OPEN_POSITIONS: z.coerce.number().min(0).default(5),
  MAX_CONSECUTIVE_LOSSES: z.coerce.number().min(1).default(3),
  MAX_DAILY_APPROVED_SIGNALS: z.coerce.number().min(1).default(50),
  RISK_KILL_SWITCH: z
    .string()
    .optional()
    .transform((s) => s === "1" || s === "true"),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const p = schema.safeParse(process.env);
  if (!p.success) throw new Error("Invalid env risk-engine");
  return p.data;
}
