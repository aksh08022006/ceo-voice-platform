# Fixture benchmark report

**Suite:** `ceo-voice-core-v1`  
**Status:** synthetic harness verification  
**Baseline:** deterministic evaluator without an LLM judge

| Case label | Score | Status | Expected findings |
|---|---:|---|---|
| Ali Ghodsi | 0.9074 | warning | voice drift, unsupported generation |
| Matei Zaharia | 0.9074 | warning | voice drift, unsupported generation |
| Jensen Huang | 0.9074 | warning | voice drift, unsupported generation |

These are routing labels over the same synthetic fixture, not samples of the named leaders. The
identical score is expected and proves repeatability, not voice quality. The evaluator correctly
warns that Tier-1 structural metrics cannot support a generation-authority or authenticity claim.

No real-person accuracy is claimed. A publishable benchmark must supply a legally approved corpus,
held-out material, human ratings, inter-rater agreement, explicit baselines, and confidence
intervals. The machine-readable counterpart is [`fixture-report.json`](fixture-report.json).
