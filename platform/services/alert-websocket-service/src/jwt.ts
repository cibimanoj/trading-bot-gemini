import { createHmac, timingSafeEqual } from "node:crypto";

/** Minimal HS256 JWT verify (payload.sub + exp) — align with user-service signing. */
export function createVerifier(secret: string): (token: string) => boolean {
  return (token: string) => {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const [h, p, s] = parts;
    const sig = createHmac("sha256", secret).update(`${h}.${p}`).digest("base64url");
    const a = Buffer.from(sig);
    const b = Buffer.from(s);
    if (a.length !== b.length) return false;
    if (!timingSafeEqual(a, b)) return false;
    try {
      const payload = JSON.parse(
        Buffer.from(p, "base64url").toString("utf8"),
      ) as { exp?: number };
      if (payload.exp != null && payload.exp * 1000 < Date.now()) return false;
      return true;
    } catch {
      return false;
    }
  };
}
