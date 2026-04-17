import { z } from "zod";

const schema = z.object({
  KAFKA_BROKERS: z.string().default("localhost:9092"),
  GROUP_ID: z.string().default("signal-engine"),
  MIN_CONFIRMATION_FACTORS: z.coerce.number().min(1).max(8).default(3),
  MIN_COMBINED_CONFIDENCE: z.coerce.number().min(0).max(100).default(48),
  ML_ONLY_MIN_CONFIDENCE: z.coerce.number().min(0).max(100).default(50),
  IS_EXPIRY_DAY: z
    .string()
    .optional()
    .transform((s) => s === "1" || s === "true"),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const parsed = schema.safeParse(process.env);
  if (!parsed.success) throw new Error("Invalid env signal-engine");
  return parsed.data;
}
