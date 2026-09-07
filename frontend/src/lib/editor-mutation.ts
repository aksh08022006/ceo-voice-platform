type ActionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type Sender = <T>(path: string, init: RequestInit) => Promise<T>;

/** Preserve one action key across transport retries, including browser reloads when storage is available. */
export function createEditorMutation(send: Sender, storage: () => ActionStorage | null = () => typeof window === "undefined" ? null : window.sessionStorage) {
  const pendingActions = new Map<string, string>();
  return async function mutate<T>(path: string, body: unknown): Promise<T> {
    const serialized = JSON.stringify(body);
    const bytes = new TextEncoder().encode(`${path}:${serialized}`);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const fingerprint = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
    const storageKey = `ceo-voice:action:${fingerprint}`;
    let key = pendingActions.get(storageKey);
    try { key = storage()?.getItem(storageKey) ?? key; } catch { /* Retry remains stable in memory. */ }
    key ??= crypto.randomUUID();
    pendingActions.set(storageKey, key);
    try { storage()?.setItem(storageKey, key); } catch { /* Storage may be restricted. */ }
    const result = await send<T>(path, { method: "POST", headers: { "Idempotency-Key": key }, body: serialized });
    pendingActions.delete(storageKey);
    try { storage()?.removeItem(storageKey); } catch { /* Storage may be restricted. */ }
    return result;
  };
}
