import Fastify from "fastify";
import cors from "@fastify/cors";
import helmet from "@fastify/helmet";
import rateLimit from "@fastify/rate-limit";
import { loadEnv } from "./env.js";
import { verifyBearer } from "./jwt.js";

const env = loadEnv();

async function readJsonBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text.trim()) {
    return {};
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { error: "bad_gateway", detail: "upstream returned non-json" };
  }
}

async function main(): Promise<void> {
  const app = Fastify({ logger: true });
  await app.register(cors, { origin: true });
  await app.register(helmet, { contentSecurityPolicy: false });
  await app.register(rateLimit, { max: 300, timeWindow: "1 minute" });

  app.get("/health", async () => ({ ok: true, service: "api-gateway" }));

  const base = env.USER_SERVICE_URL.replace(/\/$/, "");

  app.post("/auth/register", async (req, reply) => {
    let r: Response;
    try {
      r = await fetch(`${base}/register`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req.body ?? {}),
      });
    } catch (err) {
      req.log.error({ err }, "user-service unreachable");
      return reply.code(503).send({ error: "service_unavailable" });
    }
    const body = await readJsonBody(r);
    return reply.code(r.status).send(body);
  });

  app.post("/auth/login", async (req, reply) => {
    let r: Response;
    try {
      r = await fetch(`${base}/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req.body ?? {}),
      });
    } catch (err) {
      req.log.error({ err }, "user-service unreachable");
      return reply.code(503).send({ error: "service_unavailable" });
    }
    const body = await readJsonBody(r);
    return reply.code(r.status).send(body);
  });

  app.get("/auth/me", async (req, reply) => {
    const auth = req.headers.authorization;
    const token = auth?.startsWith("Bearer ") ? auth.slice(7) : "";
    if (!token || !verifyBearer(token, env.JWT_SECRET)) {
      return reply.code(401).send({ error: "unauthorized" });
    }
    let r: Response;
    try {
      r = await fetch(`${base}/me`, {
        headers: { authorization: `Bearer ${token}` },
      });
    } catch (err) {
      req.log.error({ err }, "user-service unreachable");
      return reply.code(503).send({ error: "service_unavailable" });
    }
    const body = await readJsonBody(r);
    return reply.code(r.status).send(body);
  });

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
