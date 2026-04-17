import Fastify from "fastify";
import cors from "@fastify/cors";
import websocket from "@fastify/websocket";
import { Redis } from "ioredis";
import { REDIS_CHANNELS } from "@ta/shared";
import type { WebSocket } from "ws";
import { loadEnv } from "./env.js";
import { createVerifier } from "./jwt.js";

const env = loadEnv();
const verify = createVerifier(env.JWT_SECRET);

type Client = { socket: WebSocket; alive: boolean };

async function main(): Promise<void> {
  const app = Fastify({ logger: true });
  await app.register(cors, { origin: true });
  await app.register(websocket);

  const clients = new Set<Client>();

  const sub = new Redis(env.REDIS_URL);
  await sub.subscribe(
    REDIS_CHANNELS.SIGNALS,
    REDIS_CHANNELS.ALERTS,
    REDIS_CHANNELS.OPTIONS,
    REDIS_CHANNELS.LOGS,
  );

  sub.on("message", (channel: string, message: string) => {
    const payload = JSON.stringify({ channel, data: safeParse(message) });
    for (const c of clients) {
      if (c.socket.readyState === 1) c.socket.send(payload);
    }
  });

  app.get("/health", async () => ({ ok: true, clients: clients.size }));

  app.get("/stream", { websocket: true }, (socket, req) => {
    const token = new URL(req.url, "http://x").searchParams.get("token");
    if (!token || !verify(token)) {
      socket.close(4401, "unauthorized");
      return;
    }

    const client: Client = { socket, alive: true };
    clients.add(client);

    socket.on("pong", () => {
      client.alive = true;
    });

    socket.on("close", () => {
      clients.delete(client);
    });

    socket.send(
      JSON.stringify({
        channel: "system",
        data: { message: "subscribed", channels: Object.values(REDIS_CHANNELS) },
      }),
    );
  });

  setInterval(() => {
    for (const c of clients) {
      if (!c.alive) {
        c.socket.terminate();
        clients.delete(c);
        continue;
      }
      c.alive = false;
      try {
        c.socket.ping();
      } catch {
        /* ignore */
      }
    }
  }, 25_000);

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

function safeParse(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
