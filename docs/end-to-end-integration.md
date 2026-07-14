# End-to-End Integration Harness

The integration harness executes the real dependency chain and writes inspectable JSON after every completed stage:

`CuratedCorpus → VoiceProfileBuilder → ViralityLibraryBuilder → ContextCompiler → RetrievalIntelligenceEngine → PromptBuilder/Renderer → GenerationEngine → GeneratedDraft`

`create_local_integration_runner` is the local composition root. It shares one VKR workspace between publication and evidence resolution, uses the production Tier-1 profile runtime, and injects one configured model provider. `IntegrationInput` is a fully pinned, JSON-loadable command; no environment-specific IDs or dates are invented during execution.

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

The full-system regression also proves every downstream boundary using a test-only approval fixture that explicitly changes permissions, authority, and confidence. This fixture is conspicuously isolated under `tests/integration`; it is not exported, used by the production composition root, or represented as scientific validation.

Production generation requires a separately governed profile-promotion milestone: calibrated confidence, nuisance robustness, distinctiveness evidence, and an auditable approval decision. The integration phase does not fabricate those claims.

The small seed datasets in `data/integration/` are readable source examples for connector/normalization demonstrations. The regression suite uses deterministic typed fixtures so hashes, IDs, timestamps, and validation outcomes remain stable.
