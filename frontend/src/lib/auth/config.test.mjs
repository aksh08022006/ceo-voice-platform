import assert from "node:assert/strict";
import test from "node:test";
import { safeReturnPath } from "./config.ts";
import { authFailureMessage } from "./errors.ts";

test("auth redirect retains local editor paths and search parameters", () => {
  assert.equal(safeReturnPath("/revoice?id=draft-1"), "/revoice?id=draft-1");
  assert.equal(safeReturnPath("/workspace?draft=abc#review"), "/workspace?draft=abc#review");
});

test("auth redirect cannot leave the application or loop into auth/API", () => {
  for (const value of ["https://outside.example", "//outside.example", "/\\outside.example", "/auth/sign-in", "/api/auth/sign-out", "/%2e%2e/auth/sign-up", null, ""]) {
    assert.equal(safeReturnPath(value), "/workspace");
  }
});


test("provider setup failures get actionable text without forwarding sensitive provider output", () => {
  assert.match(authFailureMessage({ code: "INVALID_ORIGIN", message: "debug secret token" }), /administrator needs to complete workspace setup/);
  assert.doesNotMatch(authFailureMessage({ message: "debug secret token" }), /debug secret token/);
  assert.match(authFailureMessage({ code: "EMAIL_NOT_VERIFIED" }), /Verify your email/);
});
