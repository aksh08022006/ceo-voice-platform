# End-to-End Integration Harness

The integration harness executes the real dependency chain and writes inspectable JSON after every completed stage:

`CuratedCorpus → VoiceProfileBuilder → ViralityLibraryBuilder → ContextCompiler → RetrievalIntelligenceEngine → PromptBuilder/Renderer → GenerationEngine → GeneratedDraft`

`create_local_integration_runner` is the local composition root. It shares one VKR workspace between publication and evidence resolution, uses the production Tier-1 profile runtime, and injects one configured model provider. `IntegrationInput` is a fully pinned, JSON-loadable command; no environment-specific IDs or dates are invented during execution.

Production request serving is a distinct path. `PublishedIntegrationRunner` accepts a
`PublishedIntegrationInput` containing the active HVM profile, exact curated voice corpus, active
VKR profile, content-addressed VKR analysis snapshot, exact structural corpus, and generation
request. It begins at authorization and never invokes either builder. Before context compilation it
verifies generation readiness and reconstructs the VKR analysis snapshot hash; evidence spans are
then resolved against the exact clean documents and checked by checksum. This prevents a browser
request from silently rebuilding or promoting knowledge.

Deployment packages use `PublishedProfileBundle`, a single validated contract containing the
profile descriptor, complete published HVM, exact clean voice corpus, published VKR, exact VKR
analysis, structural corpus, and matching feature registry. A small catalog contains only confined
relative bundle paths. Startup loading rejects absolute/traversing paths, duplicate slugs,
cross-tenant assembly, registry mismatches, lineage mismatches, and reconstructed analysis-snapshot
hash mismatches. Raw acquisition data is still excluded; the clean evidence corpus is included
because retrieval must verify every published span checksum without reading arbitrary source files.

Set `CEO_VOICE_API__PUBLISHED_PROFILE_CATALOG` to that catalog to activate production serving.
The API validates every bundle at startup, lists only deployed profiles, and routes requests through
`PublishedIntegrationRunner`. This mode fails configuration unless an external model provider is
enabled; the deterministic showcase provider is never used with published identity artifacts.

## Artifacts and diagnostics

Each run writes to `<output_directory>/<run_id>/`:

- `voice-profile.json`
- `virality-profile.json`
- `generation-context.json`
- `retrieval-bundle.json`
- `rendered-prompt.json`
- `generated-draft.json`
- `output-validation.json`
- `generation-report.json`
- `integration-outcome.json`

The outcome contains stage offsets and durations, corpus sizes, evidence and prompt counts, provider attempts, safe failure details, and every completed typed artifact. Writes are atomic at file level. API keys are never present in these artifacts.

## Integration finding: authorization is currently the production blocker

The unmodified Tier-1 builder deliberately publishes descriptive statistics. Its feature registry does not grant `GENERATE`, its components have `DESCRIPTIVE` authority, confidence placeholders are non-authoritative, and corpus health sets `generation_ready=false`. The harness therefore stops before context compilation with `profile_not_generation_ready`. This is correct fail-closed behavior—not an orchestration bug.

The full-system regression also proves every downstream boundary using a test-only approval fixture that explicitly changes permissions, authority, and confidence. It then serves a second request
from those already-published artifacts and asserts that the timeline contains no profile or
virality build stage. This fixture is conspicuously isolated under `tests/integration`; it is not
exported, used by the production composition root, or represented as scientific validation.

Production generation requires a separately governed profile-promotion milestone: calibrated confidence, nuisance robustness, distinctiveness evidence, and an auditable approval decision. The integration phase does not fabricate those claims.

The small seed datasets in `data/integration/` are readable source examples for connector/normalization demonstrations. The regression suite uses deterministic typed fixtures so hashes, IDs, timestamps, and validation outcomes remain stable.
