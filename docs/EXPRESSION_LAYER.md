# Expression, emoji and viewpoint

This change follows the founder's engineering PDF, especially the tonal register and emoji
requirements (pp. 1–2), the editing loop (p. 4), and the three examples (pp. 6–7).
The document supplies product requirements and historical example briefs. It is not a source
of verified personal memories, permission to publish, or a substitute for acceptance results.

## Representation

Generation now separates the supplied factual idea, editorial viewpoint and rationale, emotional
register, intensity, interpersonal warmth, observed emoji behavior, platform voice and structural
influence. Structure remains independently adjustable at 12% by default.

`ExpressionDirection` is editor intent for one post: auto, neutral, enthusiastic, grateful,
reflective, curious, concerned or determined; restrained/balanced/expressive intensity;
profile/reserved/warm interpersonal treatment; match-profile/no-emoji/at-most-one-emoji policy;
and optional viewpoint and rationale. These are product controls, not psychological measurements.
Intensity may change wording, never certainty, attribution, numbers or claim scope. A warm
comment can still disagree. No viewpoint is inferred from a role, an emoji or a demographic label.

`ExpressionProfile` is compiled from the selected leader's admitted authored writing on the
selected platform. Spoken material and other platforms cannot establish emoji habits. The
snapshot carries a version, leader ID, platform, corpus digest, distinct exact-text document
count, documents containing emoji, observed symbol inventory, per-document lexical cue counts,
and up to six source excerpts with document IDs, URLs, exact offsets and completeness flags.
Selection covers different visible cues; it does not equate a keyword with an emotion or belief.
The source counts are descriptive; exact deduplication does not establish campaign independence.

The English cue families locate enthusiasm, gratitude/credit, reflection, curiosity, concern,
qualification and expressed position. For example, “not excited” contains an enthusiasm word but
must not be labeled a positive emotional state. Full context remains available for interpretation.
Historical positions supply examples of framing, not new facts or timeless beliefs. A calibrated
semantic emotion/stance classifier has **not** been trained or validated in this release.

## Runtime and editing

The server constructs the profile; the browser cannot submit or overwrite one. Person/platform
mismatches are rejected. The direction and observed profile travel inside the sealed request and
context, including continuation. Expression guidance is mandatory and included in token budgeting.
Its full source snapshot and hash are exposed in the response for inspection. Evaluation source
inventories must include these excerpts in addition to retrieval-bundle evidence to avoid leakage.

Generation checks emoji policy and normal output limits. The bounded visible-symbol detector
recognizes common symbols, joined families, skin tones, flags and keycaps. It is a heuristic,
not a full Unicode validity implementation or an emoji sentiment lexicon. Counts and hard
constraints do not establish semantic accuracy, emotional fidelity or author recognizability.

Re-Voice takes an optional editor note. The actual edited text governs the new hook, paragraph
order, emotion, viewpoint and emoji. A note explains wording intent within editable regions;
it cannot authorize a structural rewrite. Emoji sequences must remain on their original lines
in their original order. Existing protected-region, negation, layout and revision checks remain.
The original generation's emotional direction is not reapplied over a later human edit.

## Research and limits of transfer

- **GoEmotions** (Demszky et al., ACL 2020) studies 27 emotion labels plus neutral in English
  Reddit comments. It motivates finer distinctions than positive/negative sentiment and the need
  for annotation quality. Our smaller editorial menu is a design choice; its labels have not been
  calibrated against executive posts. https://aclanthology.org/2020.acl-main.372/
- **SemEval-2016 stance detection** (Mohammad et al.) separates a position toward a target from
  sentiment, and notes that missing evidence does not imply neutrality. This motivates separate
  viewpoint/rationale fields and abstention about unexpressed beliefs. Its dataset and results
  are not CEO-writing validation. https://aclanthology.org/S16-1003/
- **Not Just Iconic** (O'Boyle and Doyle, WASSA 2023) finds interpretation differences with
  platform use and familiarity for WeChat emoji. This supports contextual treatment instead of
  a universal emoji-to-emotion mapping; it is not a study of Ali or Matei.
  https://aclanthology.org/2023.wassa-1.39/
- **Personalized Text Generation with Fine-Grained Linguistic Control** (Alhafni et al., 2024)
  motivates interpretable attributes across lexical, syntactic and rhetorical levels. Our added
  controls are an engineering extension, not a replication of their training experiments.
  https://aclanthology.org/2024.personalize-1.8/
- **LaMP** (Salemi et al., ACL 2024) motivates retrieval-based personalization with controlled
  evaluation. We retained the existing retrieval architecture; we do not claim a demonstrated
  hybrid-RAG improvement or a fine-tuned model. https://aclanthology.org/2024.acl-long.399/

## Acceptance

Frozen real-provider runs and the founder review packet distinguish length/layout checks,
meaning defects, assistant editorial review and pending founder scores. The first expression
run is retained even though it was too corporate and introduced unsupported benefit claims.
Prompt revision 1.5 clarifies first-person editorial copy, discourages filler and separates
acquiring teams from integrating projects, and system composition from proven performance.
Revision 1.7 makes explicit requested length take precedence over historical length averages
and gives each emotional register a concrete writing instruction. An explicit curious register
can use a question even when questions are uncommon in the historical profile. None of these
instructions establish semantic compliance without reviewing the actual generated text.

The PDF's primary gate remains founder scores averaging at least 4/5 for voice accuracy, post
quality and naturalness. Software test coverage and successful model requests cannot satisfy
that gate. A third independently sourced leader, 20+ suitable judge references per evaluation,
and an actual engagement corpus for the 100-profile structure study remain separate work.

## Repeat the live examples

From the linked repository with Vercel CLI access:

```sh
.venv/bin/python scripts/run_founder_examples.py \
  --deployment https://ceo-voice-platform-api-ruddy.vercel.app \
  --output work/founder-acceptance
```

This performs six real-provider workflow requests: the two exact PDF briefs, two sequential
editing passes, and a curious/concerned paired brief. Model-side repair can make additional
provider calls. Raw continuation-bearing files are mode 0600; keep the output in ignored
`work/`. Do not publish raw request/response files. Sanitized result files omit continuation
secrets. The meeting story is explicitly synthetic editor input for a structural test, not a
verified event. Frozen brief definitions are in `data/benchmarks/founder-pdf-examples.json`.

The new claim-cue checker targets a bounded class of unsupported benefit and firsthand-result
phrases. It can miss paraphrases and can conservatively flag legitimate paraphrases; passing it
is not semantic approval. The retained 1.6 Flash-Lite run still demonstrates this limitation.

Gemini provider handling now exposes a configurable thinking level, rejects non-complete
finish reasons, excludes thought parts from draft text, and counts reasoning output tokens.
Re-Voice uses the configured output budget too. This prevents a short legacy budget from
silently turning a truncated or reasoning-only response into a supposed completed draft.

The deployment experiments also separated transport failures from quality failures: Gemini 2.5
returned HTTP 404, Gemini 3.8 returned HTTP 503, and Gemini 3.7 produced usable responses but
also temporary HTTP 503 failures. One local run encountered DNS failure. These are retained,
not scored as bad writing or excluded to manufacture a success rate. Gemini 3.7 subsequently
returned HTTP 429 quota/rate-limit errors, including on the candidate with bounded retries.
The release therefore retains Gemini 3.1 Flash-Lite, with an 8192-token output budget and the
existing bounded two-retry transport policy. No new account or paid billing was enabled.
Provider availability and usage capacity are not guaranteed by a successful run.

The experiments changed several prompt and model settings during development. They are
exploratory regression runs, not a controlled ablation or evidence of a general quality gain.
The independent human gate remains open; no founder ratings have been supplied.
