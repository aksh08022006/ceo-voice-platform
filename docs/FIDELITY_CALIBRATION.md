# Initial live claim-screening calibration

Date: 7 September 2026. These are engineering regression checks, not independently adjudicated quality acceptance or an estimate of accuracy on customer work.

Eight fixed cases were selected before testing: a supported causal statement, an explicitly prohibited causal statement, a supported Unicode example, a prompt-injection example, and four unchanged problematic drafts retained from the earlier live campaign. The expected labels are stored in `tests/fixtures/fidelity/benchmark.json` with their annotation status.

| Experiment | Model | Result |
| --- | --- | --- |
| Original strict offset contract | Gemini 3.1 Flash-Lite | All four fully retained short responses failed structural validation because of model-authored offsets. The other four result log entries were truncated; their complete payloads were not recovered. |
| Deterministic unique-quote alignment | Gemini 3.1 Flash-Lite | Four short cases matched their expected disposition. Of four known problematic real drafts, two incorrectly received `clear` and two returned invalid-review errors. |
| Stronger current-model attempt | Gemini 3.8 Flash | Eight provider errors; no semantic result. These errors were not retried, and their HTTP status was not captured. |
| Pro comparison attempt | Gemini 3.1 Pro Preview | Eight HTTP 429 responses; no semantic result. The model was present in the account's provider model catalog. |

The experiments made 32 bounded model request attempts in staging builds: 16 returned generated reviewer text and 16 returned provider errors. They did not create editorial drafts, grant workspace membership or change the production aliases. The temporary build scripts were removed from the deployable application after collecting the experiment evidence.

The alignment change fixes a mechanical problem, not an entailment problem. Candidate and source text must still match exactly. Wrong hashes, unknown sources, hallucinated quotes, incomplete coverage, ambiguous quotes with invalid offsets and authority misuse fail closed. Alignment counts are retained in review metadata.

The two incorrect clear judgments mean the lightweight reviewer cannot be presented as a factual acceptance gate with measured reliability. A clear judgment only permits a named editor to perform their own review; it is not human approval or a claim that a draft is true. Stronger model quota and independent human adjudication remain required before a quality claim can be made.

The sample is deliberately small and includes development failures. It must not be reused as the held-out acceptance set after prompt or model tuning. Preserve all outputs and test a separate, annotated set with supported controls, unsupported claims, negation, modality, time, attribution, personal experience and causality.

Provider availability was checked against [Google's model catalog](https://ai.google.dev/gemini-api/docs/models) and the authenticated model-list API. [Gemini 3.8 Flash's official specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) identifies it as a stable September 2026 model; that listing did not establish working inference quota for this account. No model was declared superior from unsuccessful requests.
