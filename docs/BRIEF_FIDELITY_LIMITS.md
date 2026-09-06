# Brief fidelity and editorial review

Generation prompt `generation-prompt/1.3.0` explicitly preserves the brief's prohibitions, negation, uncertainty, attribution, time frame, and historical or proposed status. These requirements outrank voice, structure, variation, and elaboration to meet a length target. Composition routes are optional and require supporting facts. The prompt distinguishes an editorial angle from evidence of causality and prohibits unsupported causal explanations, measured benefits, universal performance claims, and firsthand experiences. Explicit request constraints are also included verbatim in the mandatory request section.

This is prompt hardening, not a semantic verifier. The deterministic output validator checks formatting, length, topic term overlap, selected blocked phrases, voice evidence confidence, and supported explicit phrase requirements. A passing result does not establish factual entailment, causal support, preserved uncertainty, recognizable voice, naturalness, or readiness to publish. Drafts require editorial review.

## Observed failure motivating the change

An unedited live LinkedIn draft about the February 9, 2026 Databricks disclosure preserved the date and revenue run-rate distinction but asserted that the result stemmed from engineering decisions. The supplied brief explicitly prohibited adding causal proof and supplied no evidence for that explanation. A separate X draft stated that designing compound AI systems improves results despite a prohibition on universal performance claims. These are failures to preserve the brief's limits, even though the format and topic checks passed.

## Validation boundaries

The regression tests verify that full brief text and explicit constraints survive all five composition routes, evidence pruning, and targeted format repair. They also verify that the rendered prompt retains uncertainty and attribution instructions. They do not test a real model or establish that the new prompt prevents these errors.

Exploratory reruns should use the identical brief, platform, leader, model, and generation settings; preserve original drafts; record prompt version and execution evidence; and compare exact unsupported claim spans. Two reruns cannot establish a causal improvement or an error rate. A stronger next experiment would independently label a held-out set containing supported claims, unsupported explanations, negated claims, attributed reports, conditional claims, historical announcements, and explicit prohibitions. Any future semantic gate should return specific violated constraints and draft spans, keep an uncertain state, and be calibrated against those labels before being treated as a gate. A self-rated quality score or a global earnings-keyword regex does not provide that evidence.

## Actual post-deployment observations

Six requests against deployment source `df5441b` with prompt 1.3.0 returned HTTP 200: four completed previously missing drafts, and two were separately labelled exploratory repeats with the original sixteen complete drafts preserved. Financial causality still failed: the Matei LinkedIn earnings repeat described technical rigor as necessary support for the reported growth, while the recovered Ali LinkedIn earnings draft claimed technical integration drove the reported momentum. Neither explanation was supported by the supplied facts. The Matei X industry repeat removed the earlier unconditional performance claim, but these unblinded examples establish neither an error rate nor an improvement. Successful delivery and passing format checks do not resolve semantic fidelity.
