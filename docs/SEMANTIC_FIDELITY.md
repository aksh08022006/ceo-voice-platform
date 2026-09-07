# Claim review against the brief

The optional `claim-review/1.0.0` subsystem makes a separate provider call after format validation. It assesses fidelity to the supplied brief; it does not establish that the brief itself is true. Its verdicts are `supported`, `contradicted`, `unsupported`, and `uncertain`. There is no numeric confidence or quality score. All reviews require a named human approval downstream, including a review with status `clear`.

## Authority and coverage

The reviewer receives the complete request topic, explicit request constraints, and retrieved material explicitly marked `FACTUAL_SUPPORT`. Writing examples and voice profiles are excluded. A comment parent has `attributed_context` authority: it can support an attributed statement about what the parent author said. Code rejects citations to that source for ordinary factual or editorial claims. Quoting someone is not evidence that their underlying claim is true.

Code defines sentence/newline units and assigns stable IDs. The reviewer must assess every unit exactly once. Atomic claim spans must cover every non-whitespace character of every unit. Exact candidate text, candidate SHA-256, source IDs, citation text, and Unicode code-point offsets are checked independently of the model. Unknown citations, duplicate units, omitted clauses, malformed JSON, duplicate JSON keys, extra fields, and invalid bounds are rejected. Sources are never silently truncated to fit a budget.

This proves structural coverage, not complete semantic understanding. A model can still label a mixed sentence incorrectly, miss an implication, or cite an exact but irrelevant passage. Overlapping spans allow separate claims sharing a subject; the full candidate is available to the reviewer so it can consider cross-sentence context. The current implementation does not include a separately calibrated discourse-relation verifier.

The review prompt explicitly addresses negation, modality, time and acquisition status, attribution, quantities and units, invented experience, and causality. It distinguishes a permitted qualified argument from a claim about measured results. It also distinguishes supported causality from an unsupported explanation and a negated causal assertion from a positive one. Embedded instructions in source/candidate text remain untrusted data.

## Engine integration and failure behavior

```python
fidelity = FidelityPolicy(
    enabled=True,
    model="configured-review-model",
    failure_behavior="return_for_review",
)
policy = GenerationPolicy(..., fidelity=fidelity)
reviewer = FidelityReviewer(review_provider, policy=fidelity)
engine = GenerationEngine(..., policy=policy, fidelity_reviewer=reviewer)
```

The injected review provider implements the existing `ModelProvider` interface and can use a different provider/model from the generator. Enabling fidelity without a matching reviewer is a configuration error. Default policy disables fidelity and retains existing behavior. Default failure behavior is `raise` for strict callers.

In editor mode, `return_for_review` uses the existing bounded generation-repair budget for substantive failed verdicts. Once exhausted, it retains the last candidate and its `blocked` review. Malformed responses, provider failures, and timeouts produce `error` with no accepted assessment and no repair call. Editor mode retains that candidate immediately for manual correction; strict mode raises. `approval_eligible` is false for both `blocked` and `error`; `human_approval_required` is always true. Neither mode authorizes publication. The application must enforce authenticated, named approval for the exact reviewed revision.

`GenerationReport.final_validation` remains the actual format/topic validation. `fidelity_review` independently records semantic status; it never turns failed review into successful format validation. Per-attempt reviews retain failed candidates' spans, usage, and reviewer provenance. Final review binds the exact normalized draft. Existing serialized drafts without these fields remain readable with `None`, meaning unreviewed. Individual compiled constraint results now use `satisfied=None` where no individual verifier exists, instead of reporting every compiled rule satisfied.

Each candidate gets at most one review call, with no review retries or JSON salvage. Input bytes, candidate length, units, sources, response bytes, output tokens, and time are bounded. Generation retries reuse the same semantic repair guidance after a transient provider failure. The report exposes actual generation/review call counts and their configured maxima. Token totals sum returned usage; provider failures can have unknown usage, so these are not a guarantee of billed cost. Review errors retain unknown usage as `None`.

Offsets are Python Unicode code points, end exclusive. JavaScript consumers should slice `Array.from(text)` or convert code-point offsets explicitly; ordinary string slicing uses UTF-16 code units and differs for emoji.

## Evidence and calibration

The 30 cases in `tests/fixtures/fidelity/benchmark.json` include 26 authored controls and four full unedited drafts from the real generation campaign. They cover supported and unsupported causality, negated causality, hedging, qualified opinion versus measured outcomes, financial quantities, historical dates, acquisition status, attribution, parent claims, invented and supplied firsthand experience, conflicting evidence, Unicode, prompt injection, and a mixed conjunction. Labels are engineering regression annotations, not independently adjudicated human ground truth. The real failures are retained with their original candidate hashes.

Unit tests inject fake verdicts to test strict parsing, coverage, authority, budget behavior, error isolation, retries, candidate retention, old draft compatibility, and usage accounting. They do not measure a model's accuracy. No production review calls were made while implementing this subsystem.

Before treating the reviewer as an acceptance gate, obtain independent editor annotations on the fixtures and a held-out set of complete posts/comments, resolve disagreements with evidence, and freeze the evaluation version. Measure false clearance and false blocking separately, including errors/unavailable reviews and span coverage failures. Review all previously observed financial-causality errors and supported controls. Keep same-model generation/review clearly labelled; a different model is useful experimental separation but not independent human validation. Do not tune prompts on the held-out acceptance set or omit malformed reviews from the reported denominator.

## Research basis and limits

FActScore motivates decomposing a mixed generation into smaller factual claims and evaluating support relative to a specified knowledge source. Its biography/Wikipedia evaluation does not establish accuracy for this application's brief constraints, opinions, or executive posts. We use claim-level evidence rather than adopting its scalar score. [Min et al., 2023](https://aclanthology.org/2023.emnlp-main.741/).

VeriScore distinguishes verifiable statements from subjective advice and other non-factual content, while retaining context for reference resolution. Our inference for this product is to assess permitted editorial expressions against the brief rather than pretending they have empirical proof; invented personal experiences must still be blocked when not supplied. [Song et al., 2024](https://arxiv.org/abs/2406.19276).

MONTAGELIE shows that individually supported facts can produce a misleading narrative when their ordering and relationships change. This motivates retaining the whole candidate and explicitly testing causal/temporal relationships; atomic coverage alone is insufficient. We have not implemented or replicated DoveScore. [Zheng et al., 2025](https://aclanthology.org/2025.emnlp-main.558/).

DeepFact proposes versioned, auditable factuality benchmarks whose disputed labels can be revised through evidence-based adjudication. Its deep-research results are not transferable performance claims for this project; they support maintaining revisable labels and independent audits rather than treating first-pass model or engineer labels as unquestionable ground truth. [Huang et al., 2026](https://aclanthology.org/2026.acl-long.1586/).
