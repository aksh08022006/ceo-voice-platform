# Data Pipeline

## Scope and invariant

The ingestion subsystem converts heterogeneous public source material into validated, versioned,
source-independent documents. It does not scrape websites, call provider APIs, generate
embeddings, infer voice, or expose an HTTP endpoint. Those concerns attach through later adapters
and services without changing this pipeline's stages.

The primary invariant is: **raw source bytes are retained before any lossy transformation, while
canonical text is changed only to remove transport artifacts**. Punctuation, capitalization,
emoji, sentence fragments, paragraph boundaries, repetition, and intentional whitespace remain
available to future voice analysis.

## Processing flow

```mermaid
flowchart LR
    C["Source connector"] --> S["SourceItem envelope"]
    S --> O["Ownership and source scope guard"]
    O --> R["Immutable raw repository"]
    R --> V1["Source validation"]
    V1 --> I1["Source fingerprint decision"]
    I1 --> P["Strict parser"]
    P --> CL["Style-preserving cleaner"]
    CL --> N["Canonical normalizer"]
    N --> V2["Canonical validation"]
    V2 --> I2["Document fingerprint decision"]
    I2 --> M["Metadata extraction"]
    M --> CR["Clean and metadata repositories"]
    CR --> CP["Checkpoint commit after stream success"]
```

The scope guard runs before persistence to prevent a faulty connector from writing across tenant,
leader, or source boundaries. Once ownership is proven, raw persistence precedes validation so a
malformed but attributable artifact remains available for repair and reprocessing.

## Contracts and identities

`SourceItem` is the only envelope a connector may emit. It includes raw bytes, source identity,
ownership, format, acquisition time, optional publication and provider-modification times, source
revision, cursor, encoding hint, and provider metadata. Connector SDK payloads must not escape into
the pipeline.

Three hashes deliberately answer different questions:

| Identity | Includes | Used for |
| --- | --- | --- |
| Raw checksum | Original bytes only | Byte integrity and provenance |
| Source fingerprint | Raw checksum plus stable provider metadata and format | Refetch idempotency and metadata-only change detection |
| Document fingerprint | Clean text plus voice-relevant canonical context | Ignoring transport-only rewrites while detecting meaningful canonical revisions |

Acquisition time and cursor are excluded from the source fingerprint because they describe the
fetch operation, not the source artifact. Provider modification time is included in the source
fingerprint so a touched record is re-evaluated, but excluded from the canonical fingerprint so a
timestamp-only touch does not create a voice-document version. Transformation versions are also
excluded from the document fingerprint because a cleaner upgrade is not automatically a new
author revision; backfills must make that policy explicitly.

Connector metadata is treated as stable, content-defining provenance. Volatile counters such as
views, likes, and follower totals must not be placed in this field; they belong in a future
time-series performance/event contract. Otherwise every counter change would incorrectly create a
new source and canonical revision.

Duplicate indexes are scoped by tenant, leader, and source family. Identical words published on X
and LinkedIn are retained separately because platform behavior is evidence, not noise. Within one
source family, identical envelopes under different external IDs are skipped to avoid overweighting
duplicated exports.

Canonical document IDs are deterministic over tenant, leader, source, and external ID. A changed
document therefore receives a contiguous version under a stable ID. Raw IDs additionally include
the source fingerprint, producing a new immutable artifact only when stable source state changes.

## Module responsibilities

| Module | Responsibility | Does not own |
| --- | --- | --- |
| `connectors/base.py` | Structural async connector protocol and capabilities | Cleaning, persistence, canonical models |
| `connectors/registry.py` | Registration and lookup by stable connector ID | Connector construction or credentials |
| `contracts.py` | Immutable source, stage, document, metadata, and checkpoint contracts | Workflow decisions or database mapping |
| `outcomes.py` | Validation findings, incremental decisions, write dispositions, and run results | Stage execution or persistence |
| `fingerprints.py` | Deterministic identity inputs and hashing | Duplicate policy |
| `stages/parser.py` | Strict deterministic byte decoding | Encoding guessing or content cleanup |
| `stages/cleaner.py` | Conservative HTML, Markdown, Unicode, control, whitespace, and consecutive-paragraph cleanup | Rewriting prose or semantic correction |
| `stages/normalizer.py` | Raw projection and canonical field mapping | Persistence or provider branching |
| `stages/metadata.py` | Deterministic counts and reading-time projection | Semantic or LLM-derived labels |
| `stages/validator.py` | Non-short-circuiting source and canonical integrity checks | Repair or exception transport mapping |
| `incremental.py` | New, changed, unchanged, and duplicate decisions | Fetch scheduling or full synchronization |
| `repositories/ports.py` | Async persistence contracts | Vendor SDK or schema choices |
| `repositories/memory.py` | Concurrency-safe test and local adapters | Production durability |
| `pipeline.py` | Stage order, per-item rejection policy, and checkpoint commit | Provider-specific logic or distributed scheduling |

## Connector extension contract

The architecture explicitly supports X, LinkedIn, YouTube transcripts, podcast transcripts,
earnings-call transcripts, blogs, interviews, shareholder letters, and conference talks through
`DocumentSourceType`. This means the normalizer and canonical schema understand those families;
it does **not** imply that this repository currently ships network connectors.

To add a source adapter:

1. Implement the structural `SourceConnector` protocol with a stable `connector_id`, one
   `source_type`, declared cursor/modified-since capabilities, and an async `fetch` stream.
2. Keep authentication, pagination, provider throttling, retries, and provider-payload translation
   inside the adapter.
3. Emit no more than `FetchRequest.limit`, preserve original bytes, use provider-stable external
   IDs, and provide `source_modified_at` only when the provider actually exposes that semantic.
4. Register the adapter in the application composition root. The pipeline requires no branch or
   edit for a second connector of the same source family.
5. Add adapter contract tests for scope, pagination, cursor replay, timestamp normalization,
   encoding, rate limits, and provider error translation.

A future source family needs an enum member and an explicit `DocumentType` mapping. This deliberate
mapping failure is safer than silently classifying a new source as generic text.

## Cleaning policy

The cleaner removes transport representation, not author expression:

- HTML parsing discards tags, scripts, styles, and templates while retaining block boundaries.
- Markdown cleanup removes fences and presentation markers while retaining visible label text.
- Unicode is normalized to NFC; non-breaking spaces and byte-order marks are normalized.
- Unsafe control characters are removed, but tabs and newlines remain.
- Line-ending encodings and whitespace-only transport lines are normalized without stripping
  meaningful line content.
- Only consecutive, sufficiently long, exact duplicate paragraphs are removed. Non-consecutive
  repetition and short rhetorical repetition remain intact.

Encoding is strict. The parser uses a declared encoding or UTF-8 with BOM support and rejects
invalid bytes rather than introducing replacement characters. Encoding detection may be added as
an explicit, confidence-bearing parser strategy later; it must never silently rewrite bytes.

Every canonical version stores parser version, cleaner version, applied operations, and source
encoding in `transformation_lineage`, separate from provider metadata. That separation prevents a
cleaner upgrade from masquerading as a provider metadata change.

## Failure and checkpoint policy

| Condition | Raw retained | Other items continue | Checkpoint advances |
| --- | --- | --- | --- |
| Missing author, malformed timestamp/language, invalid encoding, blank decoded content | Yes | Yes | Yes, after stream completion |
| Duplicate or unchanged content | Idempotently | Yes | Yes, after stream completion |
| Tenant, leader, or source scope mismatch | No | No | No |
| Connector exceeds requested limit | Prior valid items may exist | No | No |
| Connector/provider failure | Prior items may exist | No | No |
| Repository failure | Depends on completed writes | No | No |
| Successful empty or non-empty stream | As applicable | Yes | Yes |

Per-item rejections are explicit in `IngestionRunResult`; they are not converted to successful
documents. Advancing past a malformed item prevents one poison record from blocking a connector
forever. A production workflow must durably retain run outcomes or emit them to an operational
event stream so rejected raw IDs can be repaired and replayed.

The checkpoint is written only after the async connector stream completes. If a run fails after
some documents were stored, the checkpoint stays behind; a retry encounters idempotent raw writes
and unchanged decisions before completing the checkpoint. Caller-supplied cursor or modified-since
bounds override stored checkpoint values, enabling controlled backfills.

Provider modification time is distinct from publication time. The pipeline advances
`modified_after` only from `source_modified_at`; it never guesses that a publication or acquisition
timestamp has provider modification semantics.

## Storage design and production adapters

The three persistence concerns are independent ports:

- raw documents contain original bytes and immutable acquisition provenance;
- clean documents contain versioned canonical text and a raw-artifact reference, never duplicated
  raw bytes;
- metadata records contain query-oriented typed projections for each document version;
- checkpoints contain connector progress scoped by connector, tenant, and leader.

The in-memory adapters are concurrency-safe and make unit tests and local composition executable.
They are not a production database. At scale, raw bytes should live in encrypted object storage,
canonical documents and metadata in a relational store, and checkpoints in a transactional store
with uniqueness constraints matching the repository keys.

`pipeline.py` writes metadata before the clean projection so a retry can repair a failed clean
write idempotently. A production relational adapter should replace the two calls with one database
transaction or transactional-outbox operation. Concurrent processing of the same source identity
must use an advisory/distributed lock or optimistic retry around the unique version constraint.
Neither concern belongs in the source-independent pipeline.

Recommended partition keys at larger scale are tenant first, leader second, with source and
external ID supporting the latest-version index. Raw object keys should include tenant and a
content-addressed ID. Retention, legal deletion, access control, and encryption policies belong to
the concrete storage adapters and data-governance layer.

## Testing strategy

The test suite treats every stage independently and then proves orchestration behavior end to end:

- strict contract and timestamp validation;
- connector protocol substitutability and registry errors;
- encoding, HTML, Markdown, Unicode, whitespace, control-character, and paragraph policies;
- canonical mapping for every required source family;
- checksum and fingerprint behavior, including metadata-only and transport-only changes;
- tenant scoping, version contiguity, idempotent writes, and monotonic checkpoints;
- new, changed, unchanged, same-source duplicate, and cross-platform preservation decisions;
- raw retention for malformed content;
- no checkpoint advancement on connector, contract, overflow, or storage failure;
- checkpoint seeding and parser bypass for unchanged content.

Tests use deterministic clocks and in-memory ports. Production adapters will require a shared
contract-test suite plus integration tests against their real database/object-store semantics.

## Deliberate limitations and extension points

This phase does not provide network connectors, scraping, full two-way synchronization, deletion
tombstones, workflow scheduling, a durable rejection queue, database/object-store adapters,
malware scanning, PII policy, language detection, transcript speaker diarization, or embeddings.

The next ingestion extensions should be introduced only when their operational owner exists:

- a durable run/outcome repository or event stream for replay and observability;
- a transactional production storage unit of work;
- deletion and source-tombstone semantics;
- bounded batch concurrency and per-source distributed locks;
- metrics for stage latency, rejection codes, bytes, versions, and checkpoint lag;
- transcript-specific adapters that retain speaker and segment timestamps as structured metadata;
- versioned backfill policy when parser or cleaner behavior changes;
- content-policy and data-governance enforcement before downstream eligibility.

Embeddings attach after validated clean storage. They must consume an explicit canonical document
version and document fingerprint; they do not belong inside ingestion and cannot determine whether
source processing succeeded.
