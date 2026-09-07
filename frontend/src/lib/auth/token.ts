import { AUTH_ENABLED } from "./config";

/** Neon /next injects set-auth-jwt into session.token, matching its internal getJWTToken(false). */
export async function getJWTToken(): Promise<string | null> {
  if (!AUTH_ENABLED) return null;
  if (typeof window === "undefined") throw new Error("Sign in through the workspace to continue.");
  const { authClient } = await import("./client");
  const { data, error } = await authClient.getSession();
  if (error) throw new Error("Your session could not be checked. Please try again.");
  const token = data?.session?.token;
  if (!data?.user || typeof token !== "string" || token.split(".").length !== 3) {
    throw new Error("Your session has expired. Sign in again to continue.");
  }
  return token;
}
