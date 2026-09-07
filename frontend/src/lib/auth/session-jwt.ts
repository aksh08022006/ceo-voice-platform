type SessionResult = { data: { user?: unknown } | null; error: unknown };
type TokenResult = { data: { token?: unknown } | null; error: unknown };

/** The SDK aliases /token to its in-memory session cache; use the same-origin proxy directly. */
export async function requestSessionJWT(fetcher: typeof fetch = fetch): Promise<TokenResult> {
  try {
    const response = await fetcher("/api/auth/token", {
      method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) return { data: null, error: true };
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("token" in body)) return { data: null, error: true };
    return { data: { token: body.token }, error: null };
  } catch {
    return { data: null, error: true };
  }
}

/** Session cookies can contain opaque session tokens. Only /token supplies an API JWT. */
export async function resolveSessionJWT(
  readSession: () => Promise<SessionResult>,
  readToken: () => Promise<TokenResult>,
): Promise<string> {
  const session = await readSession();
  if (session.error) throw new Error("Your session could not be checked. Please try again.");
  if (!session.data?.user) throw new Error("Your session has expired. Sign in again to continue.");
  const result = await readToken();
  const token = result.data?.token;
  if (result.error || typeof token !== "string" || token.length > 16000 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) {
    throw new Error("Your API access token could not be issued. Please sign in again.");
  }
  return token;
}
