# ADR 001: Optional evidence ranking and blinded comparisons

- Status: Accepted for development and evaluation
- Date: 2026-09-07
- Scope: Retrieval ranking, application embedding preparation, and comparative human evaluation

## Context

The existing context/retrieval path has useful authority, evidence, release, and budget guarantees.
It uses deterministic metadata and exact-token overlap to rank supporting spans. The product needs
a way to test whether lexical or semantic relevance improves drafts without weakening those
guarantees or claiming that topical similarity is personal voice.

The existing evaluator measures candidate conformance and synthetic regression behavior. It does
not supply empirical evidence that a more complex architecture beats simpler alternatives.

## Decision

Keep `baseline` as the default. Add `bm25` and `hybrid` as explicit optional ranking modes over the
same already eligible evidence spans. Hybrid uses BM25 and cosine ranks fused by weighted reciprocal
rank fusion. Relevance contributes a bounded share of the candidate score; mandatory coverage,
authority, platform, diversity, and budget selection remain in their existing owners.

Pure retrieval accepts dense snapshots rather than calling an embedding service. Those inputs pin
tenant, model, revision, dimensions, exact candidate membership/content hashes, and query hash.
Invalid or missing vectors fail closed. An injected application preparer may make explicitly
enabled, bounded OpenAI-compatible embedding requests and cache the results. Credentials and
provider payloads remain outside domain contracts.

Add an independent `experiments` package that accepts actual supplied outputs, validates declared
train/context/held-out separation, prepares reproducible blinded baseline comparisons, and scores
submitted human ratings with uncertainty. Keep reviewer ballots separate from their private arm
mapping. Synthetic runs remain labeled, missing ratings remain missing, and report completion is
coverage rather than approval or proof of statistical power.

## Alternatives considered

| Alternative | Decision and reason |
|---|---|
| Replace retrieval with full-corpus vector search | Deferred. It changes corpus/candidate boundaries and does not establish voice fidelity. |
| Add a vector database immediately | Deferred. The bounded candidate set can be scored directly; durable large-corpus search needs separate measured requirements. |
| Treat lexical similarity as a fallback dense vector | Rejected. It would misrepresent hybrid behavior and hide provider or snapshot failures. |
| Fine-tune a model first | Deferred until attributable data and controlled comparisons demonstrate a need. |
| Approve quality using only existing synthetic scores or an LLM judge | Rejected. Neither establishes the human editorial outcome. |

## Consequences and limits

The new modes are reversible experiments; they are not proven quality improvements. Topically close
evidence may increase copying or encourage content leakage. Dense provider recomputation can vary;
an operator-supplied revision records an intended version but cannot prove unchanged provider
weights. Embedding preparation adds network cost and transfers eligible text to the configured
provider only when hybrid mode is enabled.

The comparison workflow does not generate candidates, validate a hidden upstream training run, or
ensure raters are qualified. Operators still pin generation settings, account for failed runs,
provide independent reference writing, measure editing effort/cost/latency, and design a sufficient
panel. Declared source/group/hash checks do not detect every semantic duplicate or topic leak.

## Verification and reversal

Tests must show baseline compatibility; known BM25/cosine behavior; deterministic fusion and ties;
rejection of stale, cross-tenant, dimension, membership and vector errors; and unchanged coverage
and budget guarantees. Embedding adapters need response, batching, cache, and failure tests.
Experiment tests cover source leakage, stable blinding, invalid ratings, missing coverage,
dependence-aware comparisons, and explicitly synthetic smoke reports.

To reverse runtime ranking, set `CEO_VOICE_RETRIEVAL__MODE=baseline`. Existing HVM/VKR releases and
source data need no mutation. Retain the experimental reports and exact input snapshots for audit;
changing an algorithm or interpretation requires a new version rather than rewriting old results.
