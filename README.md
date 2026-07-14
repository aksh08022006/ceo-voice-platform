# CEO Voice Platform

A production-oriented foundation for an executive voice intelligence platform. The long-term
system will represent a leader's writing as versioned, evidence-backed micro-patterns and keep
voice, factual grounding, platform structure, and evaluation as independent concerns.

This repository has completed the **Data Pipeline**, **Hierarchical Voice Model knowledge
representation kernel**, and **Voice Analysis Framework**. It contains an executable,
source-independent ingestion framework, a typed and release-governed voice representation, and a
dependency-aware compiler that produces deterministic evidence-backed observations. It does not
contain network acquisition, statistical inference, LLM behavior, retrieval, or generation.

## Current scope

Implemented:

- a modular `src`-layout Python package;
- environment-driven, validated settings with production safety policies;
- structured JSON and developer-console logging with request-ID context propagation;
- a common, transport-neutral exception hierarchy;
- strict contracts for documents, identities, versioned voice profiles, retrieved evidence,
  generation messages, and evaluation results;
- bounded file, text, JSON, time, retry, and hashing utilities;
- deterministic dependency locking, pre-commit hooks, and GitHub Actions quality gates;
- unit tests with strict configuration and a 95% minimum branch-coverage threshold;
- a structural async connector contract and connector registry;
- strict parsing and style-preserving HTML, Markdown, Unicode, control, whitespace, and duplicate-
  paragraph cleaning;
- raw, source-envelope, and canonical fingerprints with source-scoped duplicate policy;
- source and canonical validation, deterministic metadata extraction, and version normalization;
- async repository ports with concurrency-safe in-memory adapters;
- incremental new, changed, unchanged, and duplicate decisions;
- failure-safe pipeline orchestration with raw retention and post-stream checkpoints;
- a declarative, content-addressed feature registry spanning all independent HVM dimensions;
- immutable identity, lineage, evidence, observation, aggregate, residual, interaction, prototype,
  constraint, preference, confidence, drift, release, and retrieval-projection contracts;
- producer-neutral observations and dependency-inverted ports for future estimators;
- a compiler that orchestrates injected capabilities without implementing measurement algorithms;
- exhaustive structural validation across registry, evidence, ownership, version, reference, and
  confidence boundaries;
- append-only release lifecycle management with approval, activation, supersession, rollback, and
  point-in-time resolution;
- provider- and storage-neutral retrieval query contracts, with no retrieval implementation.
- an immutable analyzer registry with exact feature resolution, version constraints, conflict
  detection, and dependency-level execution plans;
- asynchronous same-level analyzer execution with partial recovery, deterministic traces,
  out-of-band performance metrics, and future cache ports;
- centralized observation construction that validates the pinned feature registry and emits
  HVM-native evidence, provenance, context, producer lineage, and confidence;
- versioned document, paragraph, sentence, and line addressing with exact source offsets;
- 23 Tier 1 deterministic measurements for document size, structure, punctuation and markers,
  formatting, whitespace, reading time, and declared thread length;
- confidence-composition contracts for deterministic, statistical, classifier, LLM, and
  evidence-weighted strategies, with only declared deterministic confidence implemented.

Intentionally not implemented:

- API endpoints or an application server;
- real provider connectors, provider credentials, scraping, or network acquisition;
- stylometric inference, profile estimation algorithms, statistical fitting, or learned analyzers;
- retrieval implementations, RAG, embeddings, or vector storage;
- prompt assets, prompt assembly, LLM clients, or generation behavior;
- virality scoring or evaluation behavior;
- a frontend.

Keeping those absent is a design constraint. Later milestones can add each capability behind the
contracts and boundaries established here.

## Why this foundation is not a generic RAG skeleton

The shared model deliberately avoids representing voice as a single prose summary. The legacy
`models.VoiceProfile` remains a compatibility transport contract; the authoritative representation
is the `ceo_voice.voice` domain. It is a versioned Hierarchical Voice Model with typed distributions,
leader residuals, conditional inheritance, evidence and counterevidence, structured confidence,
interactions, constraints, and immutable release lineage. A
`RetrievedContext` labels every item by role—voice evidence, factual evidence, structural
reference, or platform reference—so downstream code never has to blend those concerns implicitly.

Canonical text also preserves leading, trailing, line-break, and paragraph whitespace. Generic
cleanup would erase formatting patterns that may later be important voice evidence.

## Repository map

```text
.
├── backend/
│   └── src/ceo_voice/
│       ├── api/          # Future transport adapters; currently no endpoints
│       ├── config/       # Typed settings and environment validation
│       ├── core/         # Constants, logging, and application exceptions
│       ├── models/       # Canonical cross-module domain contracts
│       ├── schemas/      # Boundary request/response messages
│       ├── services/     # Future use-case orchestration boundary
│       ├── ingestion/    # Source-neutral ETL contracts, stages, ports, and orchestration
│       ├── analysis/     # Analyzer registry, execution, evidence builder, and Tier 1 measurements
│       ├── voice/        # HVM contracts, registry, compiler, validation, and release governance
│       ├── virality/     # Future platform-performance boundary
│       ├── retrieval/    # Future evidence-retrieval boundary
│       ├── generation/   # Future generation orchestration boundary
│       ├── evaluation/   # Future evaluator boundary
│       ├── storage/      # Future persistence ports and adapters
│       ├── prompts/      # Future versioned prompt assets
│       └── utils/        # Narrow dependency-free helpers
├── frontend/             # Reserved frontend boundary; no application yet
├── data/                 # Local data policy and ignored runtime directories
├── docs/                 # Architecture and engineering practices
├── scripts/              # Operational-script policy; no product logic
├── tests/                # Automated tests mirroring backend concerns
├── .github/workflows/    # CI quality gate
├── pyproject.toml        # Package metadata and tool configuration
└── requirements.lock     # Reviewed Python 3.13 dependency resolution
```

## Quick start

Requirements:

- Python 3.13;
- Git;
- `make` on macOS/Linux, or the equivalent commands from
  [Development Setup](docs/DEVELOPMENT.md).

Create the isolated environment and install the locked dependencies:

```bash
make setup
cp .env.example .env
make check
```

The setup command installs the reviewed dependency lock, then installs the local package in
editable mode without resolving a second dependency graph.

## Quality commands

```bash
make format      # Apply Ruff fixes and Black formatting
make lint        # Ruff plus Black verification
make typecheck   # Strict mypy analysis
make test        # Pytest with branch coverage
make check       # Run the full local quality gate
```

Install the local hooks after setup:

```bash
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type pre-push
```

## Configuration

All runtime configuration uses the `CEO_VOICE_` prefix and `__` for nested fields. For example:

```text
CEO_VOICE_APPLICATION__ENVIRONMENT=development
CEO_VOICE_LOGGING__LEVEL=INFO
CEO_VOICE_LOGGING__FORMAT=console
```

Production configuration rejects debug mode and requires JSON logs. Model integration is disabled
by default; enabling it requires a provider, generation model, and externally supplied API key.
Secrets are represented with Pydantic `SecretStr`, excluded from source control, and must never be
added to log context.

See [.env.example](.env.example) for the complete current surface and
[Development Setup](docs/DEVELOPMENT.md#configuration) for operational rules.

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md) explains module ownership and dependency rules.
- [Data Pipeline](docs/DATA_PIPELINE.md) defines ingestion flow, identity, failure, storage, and
  connector-extension policies.
- [Engineering Blueprint](docs/ENGINEERING_BLUEPRINT.md) contains the full product architecture.
- [Computational Voice Profile Representation](docs/VOICE_PROFILE_REPRESENTATION.md) defines the
  research-backed Voice DNA ontology, evidence model, confidence, inheritance, and evaluation
  contract; it intentionally contains no extraction or generation implementation.
- [HVM Knowledge Representation Kernel](docs/HVM_KERNEL.md) explains the implemented domain graph,
  registry, compiler ports, structural validator, release lifecycle, and extension rules.
- [Voice Analysis Framework](docs/VOICE_ANALYSIS.md) defines analyzer registration, scheduling,
  evidence attribution, confidence composition, Tier 1 semantics, failure policy, and extensions.
- [Development Setup](docs/DEVELOPMENT.md) covers environments, dependencies, and commands.
- [Coding Guidelines](docs/CODING_GUIDELINES.md) defines project-wide engineering standards.
- [Contributing](CONTRIBUTING.md) defines the change and review workflow.

## License and use

The package is currently marked proprietary. Add an explicit organizational license before any
external distribution.
