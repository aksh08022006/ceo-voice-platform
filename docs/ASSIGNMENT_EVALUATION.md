# Engineering assignment evaluation

The standalone `ceo_voice.assignment` package implements the PDF's evaluation scales separately
from the existing synthetic demonstrations. A successful automated call is development evidence;
it cannot approve V1 or replace the assignment's human reviewer.

## Prepare the review package

From the repository, using the installed environment:

```sh
python -m ceo_voice.assignment prepare --third-profile additional-leader --output work/assignment.json
python -m ceo_voice.assignment schema --output work/assignment-schema.json
python -m ceo_voice.assignment report --manifest work/assignment.json --output work/assignment-report.json
```

Replace `additional-leader` with the actual third leader's profile ID. Ali Ghodsi and Matei Zaharia
are included. Preparation creates thirty **pending** cases: five X and five LinkedIn briefs per
leader, with one case per platform for product launch, acquisition, earnings, personal reflection,
and industry commentary. These are starting briefs, not claims that an event occurred. Replace
each idea with the actual supplied angle and verified facts, then add the generated draft.

The manifest contains all evidence and the JSON Schema describes every field. Preserve complete
original posts, public source URLs, publication dates, profile IDs, platforms and independence
groups. A source's `complete_original` and `provenance_verified` flags are reviewer attestations,
not automated proof of authorship. Leave them false until the source has actually been checked.

List **all** source text exposed during profile fitting, retrieval and generation in
`generation_sources`, including source IDs and independence groups. Set
`generation_sources_complete` only after checking the inventory. The evaluator checks declared
evidence; it cannot discover omitted material, falsely attested provenance or private pretraining
data. Threads, reposts and common campaign templates should share an independence group.

## Run the separate LLM judge

```sh
python -m ceo_voice.assignment judge --manifest work/assignment.json --limit 1 --output work/judgments.json
python -m ceo_voice.assignment report --manifest work/assignment.json --judgments work/judgments.json --output work/assignment-report.json
```

The judge reuses the configured `ModelProvider` adapter and `CEO_VOICE_MODEL__*` environment
settings. Use `--model` to choose a separate judge model. Credentials stay in external
configuration. With model access disabled the command writes a pending result, with no scores.
`--limit` defaults to thirty and bounds the number of cases considered. There is at most one model
call per case, no automatic retry, and a maximum 600 output tokens, further limited by the model
configuration. A one-case trial is useful before running the entire package. A limited run's report
correctly remains pending for unevaluated cases.

Each case requires at least twenty verified, complete, independent posts from the same leader
**and the same platform**. The same-platform minimum is a deliberately stricter implementation of
the PDF's “20+ real posts” instruction, so LinkedIn examples cannot substitute for missing X
evidence. Twenty eligible references are selected deterministically by source ID. More than twenty
may be supplied. The evaluator rejects reused source IDs, normalized duplicate text, repeated
source URLs, dependent groups and overlap with generation/profile source IDs, text or groups.
Duplicate normalized output/reference text is also blocked. These checks do not detect all
paraphrased or partial copying; inspect those separately.

References remain complete. If they exceed the configured conservative prompt budget, the case
remains pending rather than truncating posts or quietly using fewer than twenty. This means some
long LinkedIn reference collections need a larger configured model context. Missing inputs cause
no provider call.

The judge must return strict JSON with an integer `voice_score` from 1–10, observable written
reasoning, supplied reference IDs and limitations. Invalid JSON, out-of-range ratings, unknown
citations and provider failures record an error without a score. Successful records include
provider/model identifiers and actual token usage. Each judgment is bound to the exact candidate,
idea and complete selected reference records by a SHA-256 digest; changing them invalidates the
old score. The current prompt version is recorded in the batch.

## Record actual manual reviews

For each case add `human_review` containing the identified reviewer, timezone-aware review time,
notes and the three integer 1–5 ratings: `voice_accuracy`, `post_quality`, `naturalness`.
`candidate_sha256` binds the review to the exact draft, including formatting. Obtain it using:

```python
from ceo_voice.assignment.evaluation import candidate_sha256
print(candidate_sha256(draft))
```

The manual gate passes only when **every profile** has all ten required cases reviewed and the
mean is at least 4.0 **on each of the three dimensions**. A strong score in another dimension or
for another leader cannot hide a failing score. Missing reviews, missing cases, missing drafts or
reviews bound to previous drafts remain pending. Completed reviews below threshold fail.
Means from an incomplete subset may be shown descriptively, but cannot pass the gate. The named
reviewer and ratings are supplied evidence: the CLI does not impersonate a human reviewer or
independently authenticate the person who entered them.

The report's `status` passes only with the manual gate passed and all thirty current automated
judgments complete. No automated passing threshold is invented because the PDF specifies none.
This report evaluates the assignment's writing review package, not all production requirements,
corpus coverage, the top-100 structure library, or scientific proof of individual voice fidelity.

## Verification

The assignment tests cover the exact case matrix, scale validation, independent per-profile gates,
pending evidence, source/text/group leakage, duplicate references, stale human/model reviews,
platform matching, budget refusal, provider errors, citation validation and CLI execution. Tests
use clearly marked synthetic fixtures; their scores are never real assignment results. Combine
this workflow with `docs/experiments.md` for blinded model comparisons and human preference studies.
