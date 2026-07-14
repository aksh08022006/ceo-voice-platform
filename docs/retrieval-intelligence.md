# Retrieval Intelligence Engine

The retrieval layer converts one sealed `GenerationContext` plus its pinned HVM and VKR releases into a compact, sealed `RetrievalBundle`. Future prompt builders consume that bundle only; they do not query profiles, libraries, repositories, or raw documents.

## Boundary and rationale

The context compiler has already decided which voice features, structural patterns, constraints, and platform policy apply. Retrieval therefore enriches those decisions rather than performing a second broad search. This prevents a high-recall retriever from reintroducing irrelevant profile content or overriding governed decisions.

Published releases intentionally store content-free evidence addresses. `EvidenceMaterialReader` is the narrow adapter that resolves only cited immutable spans. It cannot enumerate or return whole raw documents. Production adapters must enforce tenant ownership, document version, span checksum, and content rights before returning `EvidenceMaterial`.

## Deterministic selection

Candidates are scored from decomposed confidence, requirement coverage, freshness, platform match, feature importance, representativeness, profile authority, and exact-token intent overlap. Fixed weights are versioned in `RetrievalPolicy`. Selection covers every voice feature and structural pattern first, then fills remaining capacity with diversity-aware candidates. Stable UUID tie-breaking makes repeated executions reproducible.

Budgets cap evidence items, characters, examples, and items per requirement. Mandatory evidence that cannot fit fails the request instead of silently weakening it. Optional candidates are pruned with explicit reason codes.

## Explainability and validation

Each selected span records its score decomposition, purpose, generation use, satisfied requirements, supported feature or pattern, and source artifact. The report retains requirement coverage, pruned candidates, governed-artifact traceability, confidence summaries, and diversity counts.

Input validation rejects inactive or mismatched releases, tenants, leaders, versions, hashes, requests, and platforms. Output contracts reject missing support, discontinuous ranks, accounting mismatches, and invalid content seals. No semantic search, embedding, model call, prompt logic, or generation behavior exists in this subsystem.

## Extension points

- Implement a persistent `EvidenceMaterialReader` over immutable clean-span storage.
- Add new deterministic factors behind a new `RetrievalEngineVersion`; never change historical scoring semantics in place.
- Add semantic candidate ranking later behind a separate policy while retaining the same contracts, traceability, budgeting, and validation boundary.
- Add rights and retention decisions in the material adapter, before text crosses into retrieval.
