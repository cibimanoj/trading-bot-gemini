import { createHmac, timingSafeEqual } from "node:crypto";

export function verifyBearer(token: string, secret: string): boolean {
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [h, p, s] = parts;
  const sig = createHmac("sha256", secret).update(`${h}.${p}`).digest("base64url");
  const a = Buffer.from(sig);
  const b = Buffer.from(s);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return false;
  try {
    const payload = JSON.parse(Buffer.from(p, "base64url").toString("utf8")) as {
      exp?: number;
    };
    if (payload.exp != null && payload.exp * 1000 < Date.now()) return false;
    return true;
  } catch {
    return false;
  }
}
