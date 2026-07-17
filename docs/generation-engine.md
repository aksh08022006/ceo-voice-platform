# Generation Engine

The Generation Engine is the platform's only model-calling subsystem. It accepts one matching `GenerationRequest`, sealed `GenerationContext`, and sealed `RetrievalBundle`, and returns a validated `GeneratedDraft` with a complete `GenerationReport`.

## Prompt-last boundary

`PromptBuilder` projects the already-governed voice targets, structure targets, constraints, intent, platform contract, and selected evidence into typed sections. It never reads HVM or VKR artifacts and never creates a prose persona summary. The system instruction explicitly forbids claiming to be or mentioning the leader. `PromptRenderer` runs only after section selection and token budgeting.

The token manager reserves all instructions, voice and structure targets, output policy, and the highest-ranked voice, structural, and factual evidence. Remaining evidence is included by retrieval rank until the model context budget is full. It fails rather than dropping mandatory grounding.

## Provider boundary

`ModelProvider` is the application port. OpenAI, Anthropic, and Gemini adapters translate the same provider-neutral request through an injected JSON transport. Provider credentials never enter reports or prompt contracts. The adapters follow the providers' documented text-generation APIs: [OpenAI Responses](https://developers.openai.com/api/docs/guides/text), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages), and [Gemini generateContent](https://ai.google.dev/api/generate-content).

No vendor SDK type crosses the adapter boundary. `HttpxJsonTransport` now provides the production
HTTP implementation: a reusable async connection pool, bounded timeouts, redirect refusal,
retry-aware status classification, object-only JSON validation, and content-free errors. It never
copies provider response bodies or authorization headers into diagnostics. Application composition
selects the adapter from validated settings; domain engines still depend only on `ModelProvider`.

When model access is enabled, Generation and Re-Voice use the configured adapter. Model-disabled
showcase runs retain the deterministic provider so installation and orchestration can be tested
without credentials. Enabling a provider changes model execution only; it does not promote a
synthetic or unreviewed voice profile to verified real-person evidence.

## Validation and retries

The engine rejects mismatched request, tenant, leader, content type, thread count, platform, context
ID, or context hash before calling a provider. Output validation enforces platform, exact thread,
optional word-count, required-phrase, safety, and governed voice-confidence limits. Structural
guidance carries a bounded 0–25% influence value with a 12.5% default; it never replaces voice
targets.

Transient provider failures reuse the exact rendered prompt. Validation repair creates a new prompt version instance containing only the blocking findings; it preserves the original governed targets. Retry counts are bounded independently. Validated thread output is split only after validation.

## Explainability

Every draft reports prompt and engine versions, retrieval bundle, selected evidence, voice features, structural patterns, provider/model identifiers, attempt types, latency, token usage, validation findings, and constraint disposition. Prompts and API keys are intentionally excluded from the report to avoid storing sensitive context.

Re-Voice, evaluation, frontend workflows, and model-quality claims remain outside this subsystem;
the independent downstream engines consume its sealed draft and report.
