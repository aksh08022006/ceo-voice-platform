import assert from "node:assert/strict";
import test from "node:test";
import { requestSessionJWT, resolveSessionJWT } from "./session-jwt.ts";

test("JWT requests reach the authenticated same-origin proxy without the SDK session cache", async () => {
  const result = await requestSessionJWT(async (url, options) => {
    assert.equal(url, "/api/auth/token");
    assert.equal(options.method, "GET");
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    return Response.json({ token: "header.payload.signature" });
  });
  assert.deepEqual(result, { data: { token: "header.payload.signature" }, error: null });
});

test("token HTTP errors, invalid bodies and transport failures cannot fall back to session data", async () => {
  for (const response of [new Response(null, { status: 401 }), Response.json(null), Response.json({ session: { token: "opaque" } }), new Response("invalid JSON")]) {
    assert.deepEqual(await requestSessionJWT(async () => response), { data: null, error: true });
  }
  assert.deepEqual(await requestSessionJWT(async () => { throw new Error("transport secret"); }), { data: null, error: true });
});

test("an opaque cached session token is never forwarded as an API bearer", async () => {
  let calls = 0;
  const token = await resolveSessionJWT(
    async () => ({ data: { user: { id: "synthetic-user" }, session: { token: "opaque-session-secret" } }, error: null }),
    async () => { calls += 1; return { data: { token: "header.payload.signature" }, error: null }; },
  );
  assert.equal(token, "header.payload.signature");
  assert.equal(calls, 1);
});

test("a missing or failed session cannot request an anonymous token", async () => {
  for (const session of [{ data: null, error: null }, { data: { user: null }, error: null }, { data: null, error: { message: "provider secret" } }]) {
    let calls = 0;
    await assert.rejects(resolveSessionJWT(async () => session, async () => { calls += 1; return { data: null, error: null }; }), /session/);
    assert.equal(calls, 0);
  }
});

test("failed or malformed JWT issuance fails closed without exposing provider details", async () => {
  const session = async () => ({ data: { user: { id: "synthetic-user" } }, error: null });
  for (const response of [{ data: null, error: { message: "provider secret" } }, { data: { token: "opaque-session-secret" }, error: null }, { data: { token: "a..b" }, error: null }, { data: { token: "a".repeat(16000) + ".b.c" }, error: null }]) {
    await assert.rejects(resolveSessionJWT(session, async () => response), { message: "Your API access token could not be issued. Please sign in again." });
  }
});
