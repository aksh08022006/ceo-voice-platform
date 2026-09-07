import assert from "node:assert/strict";
import test from "node:test";
import { createEditorMutation } from "./editor-mutation.ts";

function memoryStorage() {
  const items = new Map();
  return { items, getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value), removeItem: (key) => items.delete(key) };
}

test("a lost response and reload reuse one action key; a successful new action gets a fresh key", async () => {
  const storage = memoryStorage();
  const keys = [];
  const body = { idea: "A private brief that must not appear in the action-key cache." };
  const failed = createEditorMutation(async (_path, init) => { keys.push(init.headers["Idempotency-Key"]); throw new TypeError("connection lost after dispatch"); }, () => storage);
  await assert.rejects(failed("/generate", body), /connection lost/);
  assert.equal(storage.items.size, 1);
  assert.ok(!JSON.stringify([...storage.items]).includes(body.idea));
  const resumed = createEditorMutation(async (_path, init) => { keys.push(init.headers["Idempotency-Key"]); return { id: "saved-draft" }; }, () => storage);
  assert.deepEqual(await resumed("/generate", body), { id: "saved-draft" });
  assert.equal(keys[0], keys[1]);
  assert.equal(storage.items.size, 0);
  await resumed("/generate", body);
  assert.notEqual(keys[1], keys[2]);
});

test("changed inputs get independent keys and unavailable storage still permits safe in-page retry", async () => {
  const keys = [];
  let failing = true;
  const mutate = createEditorMutation(async (_path, init) => { keys.push(init.headers["Idempotency-Key"]); if (failing) throw new TypeError("network failure"); return {}; }, () => { throw new Error("storage disabled"); });
  await assert.rejects(mutate("/revoice", { expected_revision_id: "one" }));
  await assert.rejects(mutate("/revoice", { expected_revision_id: "two" }));
  failing = false;
  await mutate("/revoice", { expected_revision_id: "one" });
  assert.equal(keys[0], keys[2]);
  assert.notEqual(keys[0], keys[1]);
});
