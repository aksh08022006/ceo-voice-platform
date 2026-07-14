# Evaluation Framework

The Evaluation Framework is an independent consumer of generated and Re-Voiced drafts. It cannot
modify prompts, retrieval, HVM, VKR, generation, or Re-Voice behavior. Its purpose is to make quality
claims measurable, repeatable, inspectable, and falsifiable rather than collapsing them into one LLM
opinion.

## Evaluation layers

Every report contains separate dimension scores for voice fidelity, structural fidelity, constraint
compliance, platform compliance, factual preservation, edit preservation, and readability.

- Voice evaluation measures only supported Tier-1 candidate statistics against compiled numeric HVM
  targets. It reports unsupported features as unobservable, measures retrieval evidence coverage,
  records descriptive lexical support, and applies a four-token near-copy guard.
- Structural evaluation runs the existing governed VKR extractors over the candidate and compares
  their exact pattern classifications with the selected structural guidance.
- Constraint and platform evaluation checks character and thread limits, safety terms, and hard or
  soft constraints whose semantics are observable from text. Opaque constraints remain explicitly
  unverified rather than guessed.
- Factual preservation extracts observable risk anchors—numbers, names, URLs, quotations, mentions,
  and hashtags—and checks whether they occur in supplied intent, factual evidence, or the human edit.
  This is a hallucination-risk signal, not a factuality oracle.
- Re-Voice evaluation measures lexical preservation, protected-region preservation, permitted-region
  activity, factual anchors, and the Re-Voice constraint disposition. Lexical similarity does not
  claim semantic equivalence.
- Readability uses bounded sentence, paragraph, and whitespace measurements. It deliberately avoids
  unsupported claims about comprehension or audience preference.

The overall score is a policy-versioned weighted mean over applicable deterministic and human
metrics. Non-applicable dimensions do not inflate it. Constraint, platform, and factual failures are
blocking. Other failed dimensions create warnings and actionable failure classifications.

## LLM and human review

`StructuredLLMJudge` reuses the provider-neutral model adapter, so existing OpenAI, Anthropic, and
Gemini adapters can serve it. Its prompt is versioned separately from generation and requests only
bounded scores, observable rationales, evidence IDs, a recommendation, and limitations. Responses
are schema validated and may cite only evidence in the retrieval bundle. Provider metadata and token
usage come from the adapter, not model-authored JSON.

Judge scores are supplementary by default and do not change the authoritative score. A versioned
policy must explicitly opt in. This prevents a nondeterministic judge from silently replacing
objective gates. Human reviews carry a candidate ID, reviewer reference, dimension ratings,
recommendation, rationale, and timestamp; mismatched reviews are rejected.

## Benchmarks and regressions

The engine supports single evaluation, concurrent ordered batches, minimum-threshold benchmark
suites, and candidate-matched regression comparison with explicit tolerances. Benchmark cases pin
their complete `EvaluationInput`, so HVM, VKR, context, retrieval, draft, and time are reproducible.

The catalog in `data/benchmarks/evaluation-suite.json` reserves cases for Ali Ghodsi, Matei Zaharia,
and Jensen Huang. It is intentionally labeled as a synthetic harness fixture. The
repository does not claim empirical real-person fidelity without legally approved, held-out corpora.
Tests execute the three-case harness and verify pass/regression behavior.

## Reports and failure analysis

Machine reports contain every metric, applicability, score, threshold disposition, explanation,
diagnostics, evidence references, release lineage, human and judge reviews, failure categories, and
recommended actions. The deterministic Markdown renderer adds voice, structure, constraint,
failure, recommendation, and traceability summaries.

Stable failures include voice drift, structural misalignment, constraint and platform violations,
factual risk, edit drift, readability degradation, insufficient evidence, and unsupported feature
measurement. Judge disagreement remains reserved for a future calibrated comparison policy and is
not emitted without a defensible detector.

## Scientific limitations

Deterministic metrics prove observable conformance, not identity authenticity. Factual anchors do not
verify propositions. Lexical preservation does not prove unchanged meaning. VKR alignment does not
prove engagement. LLM judges remain model opinions. Production claims require held-out, rights-cleared
corpora, blinded human comparisons, inter-rater analysis, confidence intervals, and cross-topic and
cross-time testing. The framework provides the execution and evidence contracts for those studies;
it does not fabricate their results.
