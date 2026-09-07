import { createNeonAuth } from "@neondatabase/auth/next/server";

let instance: ReturnType<typeof createNeonAuth> | undefined;

export function serverAuthConfigured(): boolean {
  return Boolean(process.env.NEON_AUTH_BASE_URL || process.env.NEON_AUTH_COOKIE_SECRET);
}

export function getServerAuth() {
  if (!instance) {
    const baseUrl = process.env.NEON_AUTH_BASE_URL;
    const secret = process.env.NEON_AUTH_COOKIE_SECRET;
    if (!baseUrl || !secret || secret.length < 32) throw new Error("Authentication configuration is incomplete.");
    instance = createNeonAuth({ baseUrl, cookies: { secret }, logLevel: "silent" });
  }
  return instance;
}
