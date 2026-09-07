import assert from "node:assert/strict";
import test from "node:test";
import { resolveSessionJWT } from "./session-jwt.ts";

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
