import assert from "node:assert/strict";
import test from "node:test";
import { draftTextSegments, exactSpan, publicSourceUrl } from "./editor-spans.ts";

const span = (start, end, text) => ({ start, end, text, offset_unit: "unicode_code_points" });

test("locates exact claim after astral Unicode characters and retains formatting", () => {
  const draft = "🚀 Growth\n\nRevenue may rise by 20%.";
  const result = exactSpan(draft, span(10, 34, "Revenue may rise by 20%."));
  assert.equal(result?.before, "🚀 Growth\n\n");
  assert.equal(result?.selected, "Revenue may rise by 20%.");
  assert.equal(result?.after, "");
  assert.equal(draftTextSegments(draft, span(10, 34, "Revenue may rise by 20%.")).map((part) => part.text).join(""), draft);
});

test("rejects UTF-16 offsets, stale text, empty and out-of-range spans", () => {
  const draft = "🚀 plan";
  for (const invalid of [span(3, 7, "plan"), span(2, 6, "old!"), span(2, 2, ""), span(-1, 3, "🚀 p"), span(2.5, 6, "plan")]) {
    assert.equal(exactSpan(draft, invalid), null);
    assert.deepEqual(draftTextSegments(draft, invalid), [{ text: draft, highlighted: false }]);
  }
});

test("does not normalize composed accents or CRLF source quotations", () => {
  const source = "Cafe\u0301\r\nreported 10%.";
  assert.equal(exactSpan(source, span(0, 5, "Café")), null);
  assert.equal(exactSpan(source, span(0, 7, "Cafe\u0301\r\n"))?.selected, "Cafe\u0301\r\n");
});

test("only exposes HTTP source links", () => {
  assert.equal(publicSourceUrl("javascript:alert(1)"), null);
  assert.equal(publicSourceUrl("data:text/html,anything"), null);
  assert.equal(publicSourceUrl("not a url"), null);
  assert.equal(publicSourceUrl("https://example.org/post"), "https://example.org/post");
});
