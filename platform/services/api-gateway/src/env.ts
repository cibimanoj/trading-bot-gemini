import { z } from "zod";

const schema = z.object({
  PORT: z.coerce.number().default(3000),
  USER_SERVICE_URL: z.string().url().default("http://127.0.0.1:3002"),
  JWT_SECRET: z.string().default("dev-insecure-change-me"),
});

export type Env = z.infer<typeof schema>;

export function loadEnv(): Env {
  const p = schema.safeParse(process.env);
  if (!p.success) throw new Error("Invalid env api-gateway");
  return p.data;
}
