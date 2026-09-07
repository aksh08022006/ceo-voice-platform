# CEO Voice — quality and reliability update

7 September 2026 · The Narrative Company

The update improves evidence selection, repair reliability and the feedback an editor sees. It does **not** establish the founder’s final voice-acceptance threshold. My review of the actual drafts still finds generic writing and unsupported assertions, particularly in longer posts. The app now makes more of those issues visible.

## Problems addressed

- **Structural text contaminated voice.** The writer previously received illustrative structure examples alongside personal writing. Structure-only raw text is now excluded; its layout guidance and evidence IDs remain separate from authentic voice examples and factual sources.
- **Low-value measurements displaced writing traits.** Equally confident features were selected alphabetically. Ties now prioritize sentence rhythm, paragraph habits, pronouns and rhetorical markers. Higher-confidence evidence still takes precedence.
- **Repairs lacked the rejected draft.** Each repair now receives the exact candidate and its findings. It preserves valid wording rather than starting from an empty request.
- **A failed repair could discard an available draft.** In advisory mode, a previous mechanically valid candidate can be returned if a later repair fails. Its own review and attempt number remain attached; an unsuccessful repair is not reported as a successful rewrite.
- **Retries ignored cooldowns.** The transport reads Retry-After and Google RetryInfo. Generation waits before retrying; a delay over 60 seconds is not shortened to force another call. Retries remain bounded, and waits enter latency accounting.
- **Thread review mixed formatting with claims.** Exact standalone thread separators are excluded from sentence assessment. The full candidate remains hash-bound. Gemini JSON mode prevents text-format ambiguity; the server still validates sentence coverage, IDs, authority and citations. Passing the full schema to this account returned HTTP 400, so that configuration was removed.
- **Threads used too little length headroom.** The writer targets 220 characters per thread post while retaining the 280-character hard limit. Repair findings identify the specific oversized post.

The compact prompt measured about 41% shorter in the captured Ali case (22,735 to 13,349 characters). This is a prompt-size observation, not evidence of a voice-quality improvement.

## What the editor sees

A separate, bounded model call checks statements against the saved brief, any declared factual evidence, the supplied viewpoint/rationale and attributed parent-post context. Style examples cannot establish new facts. The writer gets at most one validation-repair opportunity by default.

The generator shows one of three states: no statements flagged, sentences needing review, or review unavailable. Flagged text and reasons are expandable. “No statements flagged” is explicitly a model judgment, not factual verification or publication approval. The review remains advisory because the experiments contain both missed claims and over-rejections. The initial-generation review does not certify later human edits or Re-Voice output.

Emotion, intensity, warmth, emoji, viewpoint and rationale controls remain available. They describe editorial expression and observed writing habits; they do not measure a person’s hidden emotions or ideology. Sign-in remains disabled. No provider migration or new billing integration is part of this release.

## My assessment of the examples

These are Astra’s qualitative editorial judgments, not founder scores or validated authorship probabilities.

| Case | Observed result | Editorial judgment |
|---|---|---|
| Ali / Tabular, 150–300 words | Completed in the last six-case run. The review flagged eight sentences. | Still too much press-release language. Adds benefits, historical commitment and causal explanations beyond the brief. Needs substantive editing. |
| Matei / compound-AI thread | Final targeted run completed with posts of 198, 197 and 170 characters. The reviewer flagged the claimed need for an integrated platform and a “clear path” benefit. | Better length control; still generic in places and introduces an unsupported product requirement. Not a final voice pass. |
| First and second editing loops | Both completed, retained the supplied opening and final emoji, and reported actual wording changes with no fallback in the last six-case run. | The structural workflow works. That does not establish improved author recognizability. The supplied meeting anecdote is an explicitly synthetic editor input, not a verified biography. |
| Curious / concerned variants | Both completed with no review error; the curious draft retains “may” and asks when complexity is justified. | Closer to the intended distinction. The concerned draft emphasizes caution but loses some balance from the brief. |
| Additional briefs | Historical disclosure and disagreement were marked clear despite statements I would edit; team gratitude was flagged; the attribution run timed out. | Evidence that the review is fallible and service completion must be measured separately from quality. |

The six short calibration controls were handled as expected. Later realistic drafts exposed a false clear on invented history. After tightening the review and fixing its protocol, three targeted checks correctly blocked the problematic thread and added-history passages and allowed an aligned editorial hope. These are development calibration cases, not an independent accuracy estimate.

All retained outcomes, including failures and timeouts, appear in `QUALITY_EXPERIMENTS.json`. An HTTP 200 with a failed transport or missing content is not counted as a completed draft. Manually written editorial references remain separate from app-generated outputs.

## Research followed

The existing research note explains the transfer limits of each source:

- [GoEmotions](https://aclanthology.org/2020.acl-main.372/) motivates distinctions beyond positive/negative sentiment.
- [SemEval stance detection](https://aclanthology.org/S16-1003/) supports separating a position toward a topic from emotional tone.
- [Contextual emoji interpretation](https://aclanthology.org/2023.wassa-1.39/) motivates person/platform context rather than a universal emoji sentiment dictionary.
- [Fine-grained linguistic control](https://aclanthology.org/2024.personalize-1.8/) informs interpretable lexical, syntactic and rhetorical features.
- [LaMP](https://aclanthology.org/2024.acl-long.399/) motivates retrieval-based personalization and controlled evaluation.
- [Google’s generation API](https://ai.google.dev/api/generate-content) documents JSON response mode used by the reviewer.

No fine-tuning or newly validated hybrid-RAG gain is claimed. More model calls and larger models did not reliably solve the measured defects: alternate Gemini trials encountered provider errors, truncation and quota failures. The alternate Gateway route was not enabled.

## Verification

The full local backend run passed 802 tests with 95.21% coverage; 19 optional PostgreSQL integration cases were skipped. Lint, formatting and strict type checks passed. The subsequent thread-guidance change passed the generation suite and is covered by the final CI run. The frontend passed 14 tests, lint, type checking and production builds.

A separate headless Chrome session replayed real API responses to verify the three new review states, exact draft rendering, no sign-in link, no page errors and no horizontal overflow at 390px. Those UI checks are response replays, not new model generations. The user’s existing Chrome draft was left untouched.

Deployment is conditional on the final CI and runtime checks. The founder’s required average of at least 4/5, suitable independent voice references, and the real structural-engagement corpus remain open acceptance work. Software tests cannot substitute for those requirements.
