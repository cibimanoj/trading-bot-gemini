import { createHmac, timingSafeEqual } from "node:crypto";
import Fastify from "fastify";
import cors from "@fastify/cors";
import helmet from "@fastify/helmet";
import rateLimit from "@fastify/rate-limit";
import bcrypt from "bcryptjs";
import pg from "pg";
import { z } from "zod";
import { loadEnv } from "./env.js";
import { migrate } from "./db.js";
import { signAccessToken } from "./jwt.js";

const env = loadEnv();
const pool = new pg.Pool({ connectionString: env.DATABASE_URL });

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  role: z.enum(["admin", "analyst", "viewer"]).default("viewer"),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

function parseJwtSync(
  token: string,
  secret: string,
): { sub: string; role: string; exp: number } | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [h, p, s] = parts;
  const sig = createHmac("sha256", secret).update(`${h}.${p}`).digest("base64url");
  const a = Buffer.from(sig);
  const b = Buffer.from(s);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const payload = JSON.parse(Buffer.from(p, "base64url").toString("utf8")) as {
      sub: string;
      role: string;
      exp: number;
    };
    if (payload.exp * 1000 < Date.now()) return null;
    return payload;
  } catch {
    return null;
  }
}

async function main(): Promise<void> {
  await migrate(pool);

  const app = Fastify({ logger: true });
  await app.register(cors, { origin: true });
  await app.register(helmet, { contentSecurityPolicy: false });
  await app.register(rateLimit, { max: 120, timeWindow: "1 minute" });

  app.get("/health", async () => ({ ok: true, service: "user" }));

  app.post("/register", async (req, reply) => {
    const body = registerSchema.safeParse(req.body);
    if (!body.success) {
      return reply.code(400).send({ error: "invalid body" });
    }
    const hash = await bcrypt.hash(body.data.password, env.BCRYPT_ROUNDS);
    try {
      await pool.query(
        "INSERT INTO users (email, password_hash, role) VALUES ($1, $2, $3)",
        [body.data.email, hash, body.data.role],
      );
    } catch {
      return reply.code(409).send({ error: "email exists" });
    }
    return { ok: true };
  });

  app.post("/login", async (req, reply) => {
    const body = loginSchema.safeParse(req.body);
    if (!body.success) {
      return reply.code(400).send({ error: "invalid body" });
    }
    const r = await pool.query(
      "SELECT id, email, password_hash, role FROM users WHERE email = $1",
      [body.data.email],
    );
    const row = r.rows[0] as
      | { id: number; email: string; password_hash: string; role: string }
      | undefined;
    if (!row) return reply.code(401).send({ error: "invalid credentials" });
    const ok = await bcrypt.compare(body.data.password, row.password_hash);
    if (!ok) return reply.code(401).send({ error: "invalid credentials" });

    const token = signAccessToken(String(row.id), row.role, env.JWT_SECRET);
    return { token, role: row.role };
  });

  app.get("/me", async (req, reply) => {
    const auth = req.headers.authorization;
    if (!auth?.startsWith("Bearer ")) {
      return reply.code(401).send({ error: "missing token" });
    }
    const token = auth.slice(7);
    const payload = parseJwtSync(token, env.JWT_SECRET);
    if (!payload) return reply.code(401).send({ error: "invalid token" });
    const userId = Number.parseInt(String(payload.sub), 10);
    if (!Number.isFinite(userId)) {
      return reply.code(401).send({ error: "invalid token" });
    }
    const r = await pool.query("SELECT id, email, role FROM users WHERE id = $1", [
      userId,
    ]);
    const row = r.rows[0] as
      | { id: number; email: string; role: string }
      | undefined;
    if (!row) return reply.code(404).send({ error: "not found" });
    return row;
  });

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
