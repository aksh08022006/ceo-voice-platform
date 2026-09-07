import { AUTH_ENABLED } from "./config";
import { resolveSessionJWT } from "./session-jwt";

let inFlight: Promise<string> | undefined;

/** Fetch an authenticated JWT explicitly; Neon's cached session token can be opaque. */
export async function getJWTToken(): Promise<string | null> {
  if (!AUTH_ENABLED) return null;
  if (typeof window === "undefined") throw new Error("Sign in through the workspace to continue.");
  const { authClient } = await import("./client");
  if (!inFlight) {
    inFlight = resolveSessionJWT(() => authClient.getSession(), () => authClient.token()).finally(() => {
      inFlight = undefined;
    });
  }
  return inFlight;
}
