import { createHmac } from "node:crypto";

export function signAccessToken(
  sub: string,
  role: string,
  secret: string,
  ttlSec = 3600,
): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString(
    "base64url",
  );
  const payload = Buffer.from(
    JSON.stringify({
      sub,
      role,
      exp: Math.floor(Date.now() / 1000) + ttlSec,
    }),
  ).toString("base64url");
  const sig = createHmac("sha256", secret)
    .update(`${header}.${payload}`)
    .digest("base64url");
  return `${header}.${payload}.${sig}`;
}
