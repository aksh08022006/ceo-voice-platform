# Release gap analysis

This audit compares the repository with the assignment requirements. It is intentionally based on
observable code and artifacts, not intended future work. The architecture is frozen; remaining
work is limited to making implemented capabilities safe, reproducible, and evaluable.

## Requirement matrix

| Assignment requirement | Evidence in the repository | Status | Release action |
|---|---|---|---|
| Heterogeneous corpus ingestion | Source-neutral connector, parser, cleaner, normalizer, validator, incremental state, and repositories under `ingestion/` | Partial | Add a lawful local-export connector. Do not add credentialless social scraping. |
| Deep, evidence-backed voice representation | Versioned HVM registry, observations, distributions, residuals, interactions, constraints, confidence, lineage, and releases | Satisfied | Preserve the authorization boundary and document scientific limits. |
| Separate voice from viral structure | Independent HVM and VKR release lifecycles and compilation policies | Satisfied | No change. |
| Automated voice-profile construction | Restartable profile builder, corpus health, inspection report, immutable release publication, and CLI | Satisfied | Expose it through a clearer command surface and onboarding manifest. |
| Structural/virality library | Governed VKR extraction, aggregation, comparison, inspection, and publication | Satisfied | No change. |
| Request-specific context and retrieval | Deterministic context compiler and compact explainable retrieval bundles | Satisfied | No change. |
| LinkedIn and X generation | Provider-neutral governed generation engine and platform validators | Satisfied at subsystem level | Supply runnable composition/configuration examples; real provider calls still require user credentials and transport. |
| Human-edit Re-Voice | Protected/editable region analysis, constrained restoration, validation, and trace report | Satisfied | Include in the reproducible demonstration evidence. |
| Multidimensional evaluation | Independent voice, structure, compliance, preservation, readability, judge, benchmark, regression, and reporting modules | Satisfied | Publish clearly labelled benchmark fixtures and commands. |
| End-to-end orchestration | Integration runner produces stage artifacts, diagnostics, timing, and metrics | Partial | Package a one-command offline verification path. Production generation remains fail-closed for unapproved profiles. |
| New-CEO onboarding without code changes | Corpus build accepts manifests, but no top-level onboarding contract or readiness report exists | Partial | Add a manifest-driven onboarding command that validates inputs, builds releases, and reports readiness honestly. |
| Scalability to many leaders | Tenant-aware immutable contracts, bounded concurrency, content hashes, incremental reuse, and dependency-inverted storage | Partial | Document that bundled storage is a local reference adapter; horizontally scalable persistence is an adapter deployment concern. |
| Explainability and traceability | Evidence IDs, release lineage, selection reasons, constraint reports, prompts, generation/Re-Voice/evaluation reports | Satisfied | Add artifact walkthroughs to release documentation. |
| Testing and engineering quality | Strict typing, Ruff, Black, 95% branch-coverage gate, pre-commit, CI, unit and integration tests | Satisfied | Keep the complete gate as the release acceptance check. |
| Reproducible setup and deployment | Locked dependencies and environment template exist; containers and runtime health check do not | Partial | Add rootless multi-stage Docker packaging, Compose profiles, and a `doctor` health command. |
| Evaluator usability | Extensive subsystem docs exist, but the README is an implementation ledger and commands are fragmented | Partial | Rewrite README around install, evaluate, operate, limitations, and evidence. |
| User interface | Editorial Next.js product surface now covers generation, Re-Voice, evaluation, profiles, benchmarks, and documentation | Satisfied by later product phase | Keep synthetic transport clearly labelled until a backend HTTP API exists. |

## Tasks justified for this release

1. **Local public-export connector.** The assignment requires real heterogeneous inputs, while the
   repository only has a connector port. A bounded JSON/JSONL export connector provides a lawful,
   reproducible path for X, LinkedIn, transcript, letter, blog, and interview exports without
   bypassing platform APIs or terms of service.
2. **Manifest-driven onboarding.** Existing builders are executable but fragmented. A top-level
   manifest and report remove code changes from new-leader setup while retaining corpus review and
   generation authorization as explicit gates.
3. **Offline verification and diagnostics.** An evaluator must be able to prove installation and
   subsystem wiring without credentials. The release will distinguish deterministic fixture
   verification from a real-person production claim.
4. **Container and configuration packaging.** The assignment explicitly requires straightforward,
   cloud-neutral deployment. Containers will package the CLI and health check; they will not imply
   an HTTP service that does not exist.
5. **Release documentation and benchmark evidence.** The current README lists internals but does
   not provide a coherent evaluator journey. It must explain commands, artifacts, limitations, and
   what benchmark fixtures do and do not establish.

## Deliberately excluded

- Credentialless scraping of X, LinkedIn, YouTube, podcasts, or websites. Users must provide an
  official API adapter or a lawful export; the platform will not evade access controls.
- Automatic promotion of a deterministic Tier-1 profile to generation authority. Tier-1 metrics
  are descriptive. Human/scientific review remains required before a real person's style is used.
- A production HTTP API, frontend, vector database, semantic retrieval, cloud-specific deployment,
  or a new persistence framework. None is necessary to demonstrate the original pipeline and each
  would introduce architecture rather than finish the release.
- Claimed benchmark accuracy for Ali Ghodsi, Matei Zaharia, Jensen Huang, or any other person without
  a reviewed, licensed corpus and human evaluation. Included named-leader benchmark manifests are
  evaluation templates, not endorsement or authenticity evidence.

## Known release limitations

- The bundled workspace adapters target single-node evaluation and local operation. Their ports are
  stable, but a production deployment at millions of documents must supply durable object/database
  adapters, distributed work scheduling, and organization-specific observability.
- Model providers expose stable adapters but network transports and credentials are deployment
  responsibilities. Offline verification uses deterministic responses and is never reported as a
  model-quality benchmark.
- Public-source availability, platform permissions, copyright, consent, and impersonation policy
  remain operator responsibilities. The platform provides provenance and authorization gates; it
  cannot establish legal rights to a corpus.
