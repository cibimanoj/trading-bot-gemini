import { z } from "zod";

const schema = z.object({
  PORT: z.coerce.number().default(3010),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  JWT_SECRET: z.string().default("dev-insecure-change-me"),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const p = schema.safeParse(process.env);
  if (!p.success) throw new Error("Invalid env alert-ws");
  return p.data;
}
