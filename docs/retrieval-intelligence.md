# Retrieval Intelligence Engine

The retrieval layer converts a sealed `GenerationContext` and its pinned HVM/VKR releases into a
compact, sealed `RetrievalBundle`. Prompt builders consume that bundle only. They do not query
profiles, libraries, repositories, or arbitrary raw documents.

## Candidate boundary

The context compiler has already selected the applicable voice features, structural patterns,
constraints, and platform policy. Retrieval enriches those decisions with supporting evidence.
It cannot add unselected profile knowledge because a span scores well for a topic.

Published releases store content-free evidence addresses. `EvidenceMaterialReader` resolves only
cited immutable spans. Readers must enforce tenant ownership, document version, span checksum, and
content rights before returning `EvidenceMaterial`. These spans form the bounded candidate set;
BM25 and hybrid modes do not search a broader corpus or provide a factual knowledge search service.

## Ranking modes

`RetrievalRankingInput` is optional. Its absence, or mode `baseline`, preserves the existing
scoring path and emits no optional ranking report.

| Mode | Relevance signal | Provider requirement |
|---|---|---|
| `baseline` | Existing confidence, coverage, freshness, platform, importance, representativeness, authority, and exact-token intent overlap | None |
| `bm25` | Okapi BM25 over eligible span text, with Unicode word tokenization and a small English stopword list | None |
| `hybrid` | Weighted reciprocal rank fusion of BM25 ranks and positive cosine-similarity ranks | An exact dense evidence snapshot and matching query vector |

BM25 uses `k1=1.2`, `b=0.75`, positive inverse document frequency, and normalization against the
highest candidate BM25 score. Hybrid uses weighted reciprocal rank fusion, with default `k=60`
and equal sparse/dense weight. Nonpositive branch matches contribute no rank evidence. Stable
evidence-ID tie breaking preserves repeatability.

For optional modes, relevance is blended with the existing candidate score. The default relevance
weight is `0.35`, bounded above by `0.5`. This weighting is an experimental engineering choice,
not a calibrated probability or established optimum.

Scoring does not replace selection. The selector still covers every required voice feature and
structural pattern before filling capacity with diverse candidates. Evidence-item, character,
example, and per-requirement limits remain in force. Mandatory evidence that cannot fit fails the
request; optional evidence is pruned with reasons.

## Dense inputs and embedding preparation

The pure engine receives a `DenseEmbeddingSnapshot` and `DenseQueryEmbedding`. It makes no
network or model calls. Hybrid mode requires both and validates:

- the request tenant against both embedding inputs;
- identical model, revision, and dimensions;
- the exact request-topic hash;
- exact candidate membership and evidence content hashes;
- unique evidence IDs, finite vector components, matching dimensions, and nonzero finite norms.

A missing, stale, cross-tenant, or incompatible vector is an error. The engine does not silently
fall back to BM25 or synthesize vectors. Given identical vectors and pinned inputs, ranking is
deterministic; recomputing through a changing provider is a separate reproducibility concern.

The application can inject `RetrievalRankingPreparer` into local and published integration
runners. It prepares explicit ranking inputs before the retrieval call. The configured live
embedding boundary is enabled only for `hybrid`, uses OpenAI-compatible model configuration,
bounds input bytes, batch size and item count, and caches vectors by tenant, leader, and content
within one provider/model/revision configuration. It never truncates spans behind their hashes.
The embedding revision is an operator-declared pin, not independent verification of provider weights.

Configure BM25 without embeddings:

```text
CEO_VOICE_RETRIEVAL__MODE=bm25
```

For hybrid, supply these alongside enabled OpenAI-compatible model credentials:

```text
CEO_VOICE_RETRIEVAL__MODE=hybrid
CEO_VOICE_MODEL__EMBEDDING_MODEL=<approved-embedding-model>
CEO_VOICE_RETRIEVAL__EMBEDDING_REVISION=<reviewed-model-revision>
CEO_VOICE_RETRIEVAL__EMBEDDING_DIMENSIONS=1536
```

Dimensions must match the configured model. This mode transmits the topic and eligible source
spans to the configured provider. A generation credential alone does not activate embeddings.
See `RetrievalSettings` for blend, batch, input, and cache limits. Keep credentials in the existing
ignored environment files or deployment secret manager.

## Reports and compatibility

The bundle retains selection reasons, confidence summaries, requirement coverage, pruned
candidates, diversity, and release/evidence traceability. Optional ranking diagnostics add the
algorithm version, query hash, model/revision/dimensions and full dense-input hashes when used,
raw branch scores, ranks, fusion, and the authority/relevance blend for each candidate. Final selection may differ from
relevance order because required support and budgets still take precedence.

Integration runs persist the exact optional ranking input as `retrieval-ranking.json` beside the
bundle. In hybrid mode this includes the evidence and query vectors needed for exact ranking
replay. The aggregate integration outcome excludes this payload to avoid duplicating the vectors.
Retain these files in restricted runtime storage with the corresponding context, releases, and
evidence; the provider revision label alone cannot reproduce changed upstream model weights.

Existing input validation rejects inactive or mismatched releases, tenants, leaders, versions,
hashes, requests, and platforms. Output validation continues to check support completeness,
continuous ranks, accounting, and content seals.

## What remains to prove

Topic relevance is not voice fidelity. More semantically similar historical writing can increase
copying or topic leakage. Compare baseline, BM25, and hybrid with fixed briefs, profiles, model
settings, evidence permissions, and output budgets. Measure voice preference, meaning preservation,
copying, editor effort, latency, and cost using held-out material and actual human ratings.

The [experiment workflow](experiments.md) prepares blinded comparisons from supplied outputs and
scores real ratings. The [product thesis](NARRATIVE_PRODUCT_THESIS.md) describes the broader study
roadmap. No real-person improvement is claimed from synthetic ranking tests.

Future extensions may add a durable evidence reader, governed corpus-wide candidate discovery,
or a separately approved factual index. They must preserve the same authority, coverage, lineage,
and budget contracts and earn adoption through comparison evidence.
