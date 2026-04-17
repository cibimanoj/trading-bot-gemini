import { z } from "zod";

const schema = z.object({
  PORT: z.coerce.number().default(3002),
  DATABASE_URL: z
    .string()
    .default("postgres://postgres:postgres@localhost:5432/trading_assistant"),
  JWT_SECRET: z.string().default("dev-insecure-change-me"),
  BCRYPT_ROUNDS: z.coerce.number().default(10),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const p = schema.safeParse(process.env);
  if (!p.success) throw new Error("Invalid env user-service");
  return p.data;
}
