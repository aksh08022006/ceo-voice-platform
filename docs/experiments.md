# Blinded writing experiments

`ceo_voice.experiments` compares actual supplied drafts against a common baseline using human
ratings. It validates declared corpus separation, randomizes review sides reproducibly, and
reports case-weighted preferences with uncertainty. It does not generate drafts, call a judge,
fabricate reviews, or promote a profile.

Use it to compare generic prompting, exemplar RAG, HVM, and hybrid variants on the same briefs.
Arm names are caller-defined labels; naming an arm `hybrid` does not prove that hybrid retrieval
ran. Keep actual generation reports and model/prompt/release settings alongside the private study.

## Runnable offline smoke check

After `make setup`, from the repository root:

```bash
.venv/bin/python -m ceo_voice.experiments prepare \
  --manifest data/benchmarks/experiments/synthetic-study.json \
  --output-dir data/runtime/experiments/synthetic

.venv/bin/python -m ceo_voice.experiments score \
  --manifest data/benchmarks/experiments/synthetic-study.json \
  --ratings data/runtime/experiments/synthetic/ratings-template.json \
  --output-dir data/runtime/experiments/synthetic
```

The fixture has fictional authors and manually written candidate strings, not model-generated
results. Preparation writes nine comparison ballots. Scoring the empty rating template correctly
returns `awaiting_human_ratings` with no quality results. No provider credential is needed.

## Prepare a real study

Keep the manifest and source writing in ignored runtime storage. The schema is defined by
`ExperimentManifest` in `backend/src/ceo_voice/experiments/contracts.py`.

| Manifest field | Meaning |
|---|---|
| `experiment_id`, `tenant_id`, `synthetic` | Study identity, ownership, and an explicit fixture flag |
| `seed` | Reproducible ballot order, A/B assignment, and bootstrap sampling |
| `arms`, `baseline_arm` | Distinct variant labels and one common comparison baseline |
| `dimensions` | Independent human dimensions; defaults are `voice`, `meaning`, `fluency` |
| `sources` | Stable source ID, dependence-group ID, exact text hash, and publication timestamp |
| `cases` | Unique brief/author/platform, cutoff time, training/context/held-out references, and actual output from every arm |

Preparation rejects:

- missing or repeated source references and duplicate case identities;
- a case without an output for every declared arm;
- training or context evidence published after that case's `as_of` timestamp;
- held-out evidence published at or before the same cutoff; held-out writing must be later;
- held-out source IDs, dependence groups, or content hashes reused in training/context anywhere
  in the study.

These checks validate the declared metadata and chronological split. They cannot prove source
authorship or detect undeclared paraphrases, hidden base-model pretraining exposure, falsely labeled
groups, or company/topic leakage automatically. The operator still selects a representative later
period and verifies the source records.

Before collecting candidates, fix the primary outcome and guardrails. Use the same factual brief,
base model/settings, output constraints and reviewed profile release where the comparison calls
for them. Split related threads, campaigns and duplicate posts before fitting or retrieval. Supply
independently selected reference writing so qualified reviewers can judge the declared voice.

## Reviewer and analyst artifacts

`prepare --manifest study.json --output-dir data/runtime/study` writes:

| File | Audience and purpose |
|---|---|
| `ballots.json` | Reviewers: brief, author, platform, anonymized A/B candidates, and dimensions |
| `assignment-key.private.json` | Analyst only: case/arm mapping; created with owner-only permissions |
| `ratings-template.json` | Empty rating submission with the exact manifest fingerprint |
| `preparation.md` | Instructions and fixture disclosure |

Keep the manifest and assignment key separate from the reviewer packet because they reveal arm
identities. Each non-baseline arm is paired with the baseline for each case; this is not an all-pairs
comparison. A/B sides and ballot ordering are seeded. Candidate wording itself may still reveal a
variant, which formal label blinding cannot prevent.

Copy `ratings-template.json` to a separate ratings file. For each completed review, append an
object containing the actual `ballot_id`, stable `reviewer_id`, and `choices` mapping every dimension
to `a`, `b`, or `tie`. Do not prefill preferences. Leave an unjudgeable ballot unsubmitted; the current
contract has no separate “neither” response or partial-dimension review.

Changing any manifest content changes its fingerprint and ballot identities. Ratings from another
manifest, unknown ballots, duplicate reviewer/ballot pairs, and incomplete dimension sets are
rejected. This prevents old ratings being attached to rewritten candidates.

## Score and interpret

```bash
.venv/bin/python -m ceo_voice.experiments score \
  --manifest data/runtime/study.json \
  --ratings data/runtime/study/ratings.json \
  --output-dir data/runtime/study \
  --bootstrap-samples 2000
```

Scoring writes `report.json` and `report.md`. CLI exit `0` means the operation succeeded, including
an empty-rating report; exit `2` means a file, validation, or scoring error. The report's status is:

- `awaiting_human_ratings`: no ballots have a submitted rating;
- `partial`: some ballots are rated;
- `complete`: every ballot has at least one rating.

“Complete” does not mean adequate statistical power, a sufficient reviewer panel, authentic
authorship, or production readiness.

For each arm and dimension, the report includes win/tie/loss rates and preference
`wins + 0.5 × ties`, globally and by author. It first averages reviewers within each case and then
averages cases, so a heavily reviewed brief does not receive extra case weight. The global result
is case-weighted, not an equal-weight average of author means.

The seeded paired bootstrap resamples connected held-out dependence groups, including shared
source groups or exact content hashes, keeping related case outcomes together. It reports 95%
percentile intervals; fewer than two independent groups yields no interval. These intervals are
conditional on the supplied authors and reviewer panel. They do not model a new population of
authors or raters, and multiple comparisons are not corrected. Partial reviews may be selected
systematically rather than missing at random.

## What to measure outside this first harness

Keep meaning, voice and fluency separate. A preference score cannot override an unsupported claim
or prove reduced copying. The existing [candidate evaluator](evaluation-framework.md) can provide
complementary deterministic checks, but it is not automatically invoked by this CLI.

The study owner still records failed-generation rates, model/release equality, latency, tokens/cost,
editing time, copying, reference adequacy, rater agreement, per-platform outcomes, and the final
held-out test protocol. The current manifest requires candidate text for every arm, so a study with
failed generations needs a separate failure ledger and must not silently omit those failures when
reporting product performance. The CLI does not choose a winner or perform automatic promotion.

See the [product thesis](NARRATIVE_PRODUCT_THESIS.md) and
[retrieval ADR](adr/001-governed-retrieval-experiments.md) for the purpose and limits of this increment.
