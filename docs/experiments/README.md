# Brief-order and editorial-pass experiment

On 7 September 2026, the exact founder briefs and editing workflow were run against the baseline, a prompt-order change, and that change plus a separate brief-only editorial pass. All six API requests in each run returned 200, but unsupported claims and generic writing remained. Neither experiment was retained in production.

`brief-editor.patch` preserves the proposed implementation and tests against commit `1125122`; it is research evidence, not active code. It includes the prompt-order change and the optional editor. The prompt-order-only variant was tested before enabling the editor. The final runtime retains prompt 1.7.0 with no editorial rewrite flag.

Sanitized actual outputs are in `data/benchmarks/astra-review-2026-09-07.json`. These small exploratory runs vary in composition and sampling; no statistically established quality gain is claimed. The baseline structural-edit case reversed only one middle paragraph and therefore did not move anything. The runner now records actual movement and handles three-paragraph drafts correctly.

The production fix from this investigation removes fully protected call-to-action lines from Re-Voice’s editable region list. It avoids a provider call when no wording is permitted to change; it does not claim a voice-quality improvement.
