# A writing product for The Narrative Company

## The outcome we want

An editor should be able to turn a client's idea into a draft that sounds appropriate for that
person, preserves what they meant, and takes substantially less work to approve. Different clients
should remain distinguishable even when writing about the same facts. The product should explain
its choices well enough that an editor can correct them.

The current product supports written LinkedIn and X content. It does not synthesize audio. The
identity model can represent a person's writing, an approved executive brand, or an editorial team;
the chosen target must be explicit. CEO examples are the initial scope, not a reason to hardcode
roles or companies into generation. The original assignment PDF is not included in this checkout;
its exact submission criteria should be reconciled with this thesis when available.

## The editor's workflow

1. Onboard a declared voice using complete source writing and its provenance. Review what belongs
   to the person versus a company account, coauthor, quotation, repost, or transcript.
2. Build and inspect a versioned profile. Show supported patterns and missing evidence rather than
   a confident prose persona assembled from a few examples.
3. Select identity, platform, and idea/angle. The application resolves technical controls internally.
4. Generate a draft with separate voice guidance, structural guidance, factual context, and user
   intent. Historical voice examples do not automatically become current factual evidence.
5. Edit the draft for strategy, meaning, and accuracy. Re-Voice may restore expression within its
   protected editing boundary; the editor still reviews the result.
6. Inspect evaluation and evidence. Record actual decisions and recurring edits for a later,
   reviewed improvement cycle.

Direct publishing and automatic learning from every edit are outside the current workflow. A
successful product saves editorial effort while leaving the editor accountable for the final text.

## Why the current architecture is useful

The HVM models writing behavior and its evidence. The VKR models content organization separately.
The context compiler selects what applies to one request; retrieval chooses bounded supporting
spans; the generator consumes that result. Immutable releases and evidence addresses make failures
traceable and experiments reproducible.

The new optional BM25 and hybrid modes change how already eligible spans are ranked. They preserve
the context's authority, platform, coverage, and budget constraints. Hybrid mode combines lexical
and embedding ranks; it is not a complete factual search product or a replacement for HVM.

This architecture is a hypothesis about how to improve writing. Schema depth, test coverage, and a
working UI do not prove that it produces a more recognizable voice than a well-designed simple
prompt. The [research blueprint](ENGINEERING_BLUEPRINT.md#310-voice-fidelity-evaluation-program)
requires that comparison explicitly.

## Current evidence and limits

The repository contains a working reference workflow and synthetic regression cases. Its 11
deterministic analyzers measure 55 scalar features, including lexical, rhythm, and visible
rhetorical markers. The default builder uses arithmetic summaries and zero baselines; calibrated
cohort distinctiveness, partial pooling, nuisance robustness, interactions, and drift estimators
remain research work.

Ali/Matei development corpora are described as manually transcribed and private to local runtime
storage. They are not included in a fresh clone, and their incomplete provenance and independent
review limit their use. The three named benchmark labels reuse synthetic content. Neither those
benchmarks nor a live model call establishes real-person fidelity.

Re-Voice protects unchanged lines, formatting, and recognized factual anchors. It cannot prove
semantic equivalence from text overlap. Comparative evaluation should include changes in negation,
attribution, causality, stance, and implied claims that preserve the same names and numbers.

Reference sessions and workspaces are local/in-process. Durable storage, authentication, operational
isolation, and deletion execution must be implemented and verified before an exposed multi-tenant
deployment. See [Operations](OPERATIONS.md) for the current single-instance boundary.

## The research sequence

| Step | Question | Deliverable and adoption test |
|---|---|---|
| Establish evidence | Can we compare variants without leaking evaluation writing into profiles or context? | Complete corpus records, group/time splits, unseen briefs, frozen candidates, blinded human ballots |
| Compare retrieval | Does BM25 or hybrid improve usable supporting examples over baseline selection? | Matched baseline/BM25/hybrid outputs; voice preference and edit effort with meaning/copying guardrails and measured resource cost |
| Improve the representation | Which missing linguistic patterns explain recurring editor corrections? | A small additional feature family or cohort estimator with cross-topic and entity-masked tests, then an ablation |
| Separate meaning from realization | Do explicit claim and discourse plans reduce semantic drift enough to justify extra calls? | A staged experimental arm compared with the same one-shot model and facts |
| Consider training | Has a stable realization task accumulated enough diverse approved examples? | A fine-tuned candidate compared against the best retrieval/profile arm, including deletion, cost, and fidelity evidence |
| Expand operation | Can more roles, clients, platforms, and languages be supported without regressions? | Data-driven onboarding, durable tenant-aware services, and per-cohort acceptance evidence |

The [experiment workflow](experiments.md) implements the first comparison mechanics: declared split
validation, supplied candidate outputs, blinded ballots, and scoring real human ratings. It does
not yet execute all generation arms, enforce provider equivalence, or calculate every quality and
cost metric. Those inputs remain explicit study work rather than invented results.

Select a primary outcome before inspecting results: blind voice preference or measured editing
effort. Report meaning preservation, copying, naturalness, latency, and cost separately. Compare
the same briefs and model settings, include failures, inspect individual clients and platforms,
and reserve a final test set. Remove complexity that does not earn its cost.

## Data that makes the next study useful

- Complete authored text with original formatting, canonical source ID/URL, publication time,
  author, platform, acquisition details, and reviewed use permissions.
- Stable thread, repost, campaign, and near-duplicate groups. Split related material together
  before fitting a profile or retrieving evidence.
- A held-out writing set, unseen briefs with supplied facts, and a reviewer/delegate familiar
  with each declared voice. Model opinions are not a substitute for those ratings.
- Cross-client examples of comparable topics to test whether apparent voice is actually company
  vocabulary. Use entity masking and content-matched tasks where feasible.
- For engagement research, comparison posts and time-pinned outcome denominators; successful posts
  and raw like counts alone cannot establish an effective tactic.

The [dataset handoff](DATASET_HANDOFF.md#minimum-useful-deliveries) proposes 20 LinkedIn and 20 X
posts per leader plus a separate 20-post holdout as initial collection targets. They are not a
universal statistical sufficiency threshold. A sparse feature or context may need more independent
evidence, and some preferences can be supplied explicitly by the client instead of inferred.

The end goal is a dependable editorial collaborator whose benefit can be demonstrated on real
work. RAG, hybrid retrieval, richer features, staged generation, or training are interchangeable
means to that outcome and should be chosen by evidence.
