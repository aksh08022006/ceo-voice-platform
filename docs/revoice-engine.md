# Re-Voice Engine

The Re-Voice Engine restores governed voice targets in a human-edited draft without treating the
draft as disposable source material. It consumes the exact generated draft, sealed
`GenerationContext`, sealed `RetrievalBundle`, and the published HVM and VKR releases that produced
them. It performs no retrieval and never reads unselected profile knowledge.

## Execution contract

`EditedDraft` pairs the human revision with its exact `GeneratedDraft`. `ReVoiceInput` adds the
compiled context, retrieval bundle, published voice profile, published virality profile, and a
caller-supplied UTC execution time. Before a provider call, the engine verifies request identity,
retrieval/context seals, tenant and leader scope, platform, active release status, and exact HVM and
VKR release IDs, versions, and content hashes. It also verifies that the original generation report
references the supplied retrieval bundle.

The workflow is:

1. compare generated and edited content with deterministic character offsets;
2. classify human-modified lines as editable;
3. protect unchanged lines and semantic or formatting anchors;
4. render retrieval-approved voice targets, supporting voice evidence, constraints, and edit
   permissions;
5. request a complete revised draft through the existing provider interface;
6. validate the proposal against the deterministic edit envelope;
7. retry only with the blocking validation findings, or fail closed;
8. publish the validated draft and trace report.

No provider is called when the human made no changes. That case returns an audited no-op result.

## Preservation policy

The engine protects unchanged lines exactly. Within a human-modified line it protects URLs, email
addresses, mentions, hashtags, numbers, currency and percentage values, quotations, Markdown links,
inline code, and multi-token proper names. CTA lines are protected exactly. Newline sequences,
thread separators, line count, list/heading/quote prefixes, and inline emphasis markers must remain
unchanged. Platform and thread limits, deterministic hard constraints, a safety blocklist, and a
configurable maximum changed fraction are enforced after every provider response.

These controls are intentionally conservative. A protected anchor may reduce how much style can be
restored, but factual and human-authored intent takes precedence over voice strength.

## Explainability

`ReVoiceReport` records the original diff, editable and protected regions, changed regions, preserved
categories, constraints that governed the operation, HVM/VKR/context/retrieval lineage, provider
attempts, validation findings, latency, token usage, and an aggregate confidence value. Voice
features in the report are explicitly marked as targeted rather than independently verified. This
phase does not perform evaluation, so it does not make an unsupported claim that a particular
stylistic feature improved.

## Guarantees and limitations

The engine can deterministically guarantee structural, formatting, protected-token, release-lineage,
platform, and supported hard-constraint preservation. It cannot prove semantic equivalence or voice
quality from lexical comparison alone. It mitigates that limitation by editing only human-modified
lines, protecting factual anchors, bounding total change, and failing closed on observable drift.
Independent semantic and stylometric scoring belongs to the future Evaluation subsystem and is not
smuggled into this phase.

The provider boundary remains vendor-neutral. OpenAI, Anthropic, Gemini, and future adapters can be
used without changing Re-Voice analysis or validation behavior.
