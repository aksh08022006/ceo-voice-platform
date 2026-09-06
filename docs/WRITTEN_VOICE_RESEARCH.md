# Research brief: modeling an executive's written voice

Research date: 7 September 2026. Scope: written LinkedIn/X posts and comments for The Narrative Company. I read the repository's `docs/VOICE_ANALYSIS.md` and `docs/NARRATIVE_PRODUCT_THESIS.md` and the primary papers linked below. This is a focused engineering research review, not a systematic review of every publication. Recommendations below are engineering hypotheses to test, not demonstrated results for this repository.

## What the research supports

This is an active field spanning stylometry, authorship representation learning, controllable text generation, personalized retrieval, pragmatics, and human–AI writing. A person's written voice is better represented as a distribution of choices under a communication context than as a fixed list of personality adjectives. Measurements describe expression; they do not establish the person's private beliefs, intelligence, temperament, or psychological traits.

An actionable representation is:

`draft = realization(supplied claims, communicative intent, audience/thread context, platform, evidence-backed voice preferences, structural plan)`

That factorization is our proposed product design. Style and content cannot be perfectly disentangled automatically: author labels can correlate with company vocabulary and topics. Wang et al. experimentally probe that issue and find substantial style sensitivity for a particular authorship embedding construction, while explicitly limiting the conclusion to that construction and aggregate behavior. Ordinary semantic embeddings do not inherit this guarantee. [Wang et al., TACL 2023](https://aclanthology.org/2023.tacl-1.80/)

The current repository already has 55 deterministic scalars across 11 analyzers. These cover much of the visible lexical and rhythm baseline. The major missing layers are grammar, contextual meaning, discourse relationships, conversational purpose, and uncertainty about which patterns are stable for a person versus situational.

## A parameter taxonomy that can drive generation

This is a proposed operational taxonomy. Each inferred preference should carry source spans, independent document count, opportunity count, date range, platform/genre, measurement version, and uncertainty. A style preference should remain overrideable by the client's explicit editorial choice.

| Layer | Parameters worth modeling | Measurement and generation use | Current repository / caution |
|---|---|---|---|
| Visible shape and rhythm | Sentence-length distribution; paragraph density; isolated lines; punctuation choices; list structure; opening/ending positions | Exact text rules; per-document distributions; preserve ranges rather than forcing every post to an average | Largely present. A short comment has few opportunities; absence of a feature is weak evidence of preference |
| Lexical realization | Function-word distribution; contractions; vocabulary diversity; preferred connective phrases; technical-word tolerance; recurrent non-topical phrases | Tokenized counts, fixed-length diversity windows, cohort comparison, reviewed phrase examples | Partly present. Separate characteristic expression from product names and topical jargon |
| Grammar | POS proportions and sequences; active/passive constructions; subordinate/coordinate clauses; tense/aspect; negation; dependency depth; fragment frequency | Versioned language-specific POS/dependency parser; rate per token/clause; span evidence; parse confidence and failure flags | Missing beyond surface proxies. Parser output is statistical, not an exact observation; retain model/version lineage |
| Discourse organization | Claim→reason→example; anecdote→lesson; concession→position; question→answer; problem→action; evidence placement | Human-reviewed sentence/paragraph move labels, then a calibrated classifier or constrained LLM analyzer; retain ordered sequences and relations | Current transition lexicons cannot infer implicit relations or determine whether “but” actually introduces a concession |
| Rhetorical devices | Analogy, contrast, repetition, personal anecdote, numerical evidence, qualification, framing, explicit audience invitation | Combine visible candidates with semantic annotation; store positive and confusing negative examples; generate from a selected plan | Existing repetition/question/CTA markers cover candidates, not rhetorical intent |
| Epistemic expression | Degree of commitment; hedge scope; attributed versus personal claim; evidential source; uncertainty expressed through modality | Annotate proposition + holder + polarity + modal strength + attribution; preserve user-supplied commitment during rewriting | “May improve” must not become “will improve.” Certainty is partly meaning, not a harmless styling knob |
| Interaction and comments | Reply intent; addressed proposition; agreement/disagreement scope; acknowledgment; gratitude; question directness; contribution type; relationship to addressee | Require parent post/thread and user-selected intent; annotate reply moves in context; compare comments to comments | Missing as an explicit workflow. A comment is a conversational action, not merely a shorter post |
| Conditional preferences | Variation by platform, post/comment, audience, role, topic familiarity, campaign, and time | Keep strata; compare distributions; later partial pooling across sparse contexts; show missing context evidence | Metadata must precede estimation. Job title alone is not evidence that someone writes authoritatively or casually |

The lexical/grammar/discourse split has direct empirical precedent: Alhafni et al. control interpretable lexical, POS, dependency, and rhetorical-relation attributes in a 251-author benchmark. Their work supports testing explicit linguistic controls, but its blogs/reviews, prolific-author data, and model-specific results do not establish executive-post fidelity. Attribute matching itself is not a recognizability measure. [Alhafni et al., PERSONALIZE 2024](https://aclanthology.org/2024.personalize-1.8/)

Pragmatic interpretation requires context and interactions. Danescu-Niculescu-Mizil et al. combine lexical and syntactic cues to model politeness in requests across Wikipedia and Stack Exchange. Position and construction matter: the interpretation of “please,” “you,” and modal choices varies with their placement. Use this as evidence for contextual annotation, not as a universal rule that a phrase is polite in every LinkedIn comment. [Danescu-Niculescu-Mizil et al., ACL 2013](https://aclanthology.org/P13-1025/)

### Keep speech-only parameters outside this writing model

Audio voice also involves pitch, timbre, formants, accent, energy, timing, and acoustic prosody. A text corpus cannot measure these. Transcript punctuation can be imposed by a transcriber or ASR system; its sentence lengths and capitalization should not silently become writing preferences. If the product later adds spoken interviews, treat them as a separate source modality and use reviewed excerpts for beliefs/content or oral wording. This distinction is a scope and measurement rule, not evidence that acoustics never correlate with language.

## Evidence and sample limits

There is no scientifically justified universal number of posts that guarantees a useful voice model. The repository's suggested collection targets are sensible onboarding targets, not validation thresholds. Begin with diverse complete originals and acquire more data where uncertainty remains.

Proposed evidence rules:

1. **Count independent opportunities.** A hundred repeated campaign posts are not a hundred independent demonstrations of style. Group threads, reposts, templates, near-duplicates, and shared drafts before splitting.
2. **Report uncertainty per feature.** For a rate, retain numerator and denominator. For a per-document mean, retain count, dispersion, and an interval estimated across documents or groups. One sentence repeated within a post must not create spurious certainty.
3. **Separate commonness from distinctiveness.** “Uses short paragraphs” may be ordinary LinkedIn style. Compare with a matched authorized cohort and show both within-person consistency and deviation from the cohort. A zero baseline cannot establish distinctiveness.
4. **Use conditional evidence.** A founder may be terse in replies and explanatory in original posts. Do not mix contexts without indicating the blend. Avoid sparse cross-products of every possible condition; pool only under an explicit estimator.
5. **Treat semantic labels as measurements with error.** Keep two independent annotations on a subset, resolve disagreements, and validate the classifier by label and domain. An LLM's self-reported confidence is not calibration.
6. **Keep abstention visible.** “Insufficient observed comment examples” is an honest product state. User-declared preferences can guide a draft without being mislabeled as learned habits.

Alhafni et al. filter to substantial author histories and study varying word budgets, which is a reminder that benchmark results depend on corpus scale and selection. It is not a minimum-data prescription for this project. [Alhafni et al.](https://aclanthology.org/2024.personalize-1.8/)

## How to control topic and content confounds

Altakrori et al.'s topic-confusion setup swaps author–topic associations between training and test. Stylometric/POS feature combinations were less topic-confused than several tested neural representations. This supports a cross-topic diagnostic for our own system; it does not establish that today's LLMs are categorically worse than classical methods. [Altakrori et al., Findings EMNLP 2021](https://aclanthology.org/2021.findings-emnlp.359/)

Proposed project evaluation controls:

- Give every voice the **same supplied factual brief** and requested communicative intent. Ask whether they remain distinguishable without changing the claims.
- Hold out topics, campaigns, time periods, and near-duplicate groups before profile extraction or retrieval. Do not generate evaluation briefs by copying held-out prose into the generator context.
- Run diagnostics with names, companies, product terms, URLs, and numbers masked in evaluator inputs. Keep the original text for meaning/factual review. Masking is imperfect and should supplement, not replace, the original-text test.
- Compare with a deliberately wrong-person profile matched on topic/platform. If the wrong persona wins whenever its examples mention the same product, retrieval is likely rewarding content more than voice.
- Compare nearest-topic retrieval with diverse, context-matched voice examples. Keep factual context and voice examples in separately labeled prompt sections so historical claims are not treated as new facts.
- Measure style on both the unmasked and controlled versions. A large collapse is a diagnostic to investigate, not automatic proof of leakage.

STEL provides a useful precedent for content-controlled style tests: it pairs alternatives conveying matched content and tests dimensions including formality, complexity, contractions, and number substitution. Its four dimensions do not exhaust authorial voice. [Wegmann and Nguyen, EMNLP 2021](https://aclanthology.org/2021.emnlp-main.569/)

## Evaluation: three quality dimensions and the editorial outcome

Mir et al. separate style, content preservation, and naturalness, and show that systems can trade one against another. Their experiments use sentiment transfer, so we should reuse the separation of dimensions rather than assume their exact metrics are calibrated for executive writing. [Mir et al., NAACL 2019](https://aclanthology.org/N19-1049/)

Proposed scorecard:

| Outcome | Measurement | Failure that a single “voice score” misses |
|---|---|---|
| Voice recognizability | Blinded paired preference by client/experienced editor; optional same-topic author identification; reasons attached to spans | A draft repeats trademark jargon but sounds generic |
| Meaning preservation | Claim-level checks of polarity, attribution, numbers, modality, causality, scope; human review of omissions and invented experiences | “We tested” becomes “we proved”; cautious agreement becomes endorsement |
| Naturalness/context fit | Separate blind comparison; appropriate comment response; coherence and lack of repetitive templates | Correct feature counts with awkward or mechanically stylized language |
| Editorial value | Time to acceptable draft; accepted-without-rewrite rate; edit magnitude and reason; abandonment | Impressive similarity metrics with no time saved |
| Copying/diversity | Longest copied span, source-overlap diagnostics, repeated templates across briefs/personas | Memorized examples or convergence to one house style |
| Operations | End-to-end latency, tokens/cost, failed requests, provenance completeness | A small preference gain requiring excessive delay or cost |

Freeze candidates and randomize ordering; measure the same briefs/model settings across baseline prompt, existing profile+RAG, hybrid retrieval, and the proposed enhancement. Predeclare the primary outcome. Report paired effects and uncertainty by voice/platform; count failures. Keep a final test set untouched after choosing the winning design.

Recent evaluation research reinforces metric caution. Jangra et al.'s 2025 preprint compares overlap, style embeddings, LLM judges, and ensembles across eight domains; distinguishing personalized from unpersonalized generated text is considerably harder than distinguishing domains. Short Reddit references remain particularly difficult. Its automatically constructed binary discrimination targets do not establish client-perceived authenticity, so a blended metric panel still needs real editors. [Jangra et al., 2025 preprint](https://arxiv.org/abs/2508.06374)

A 2026 preregistered study with 81 participants found that editing LLM drafts improved measured style similarity and perceived suitability, while some LLM stylistic influence remained. The authors acknowledge only two unassisted references per participant and a mismatch of writing tasks. For our product this argues for tracking actual acceptance and editing behavior alongside external metrics, with neither overriding the other. [Baumler et al., ACL 2026](https://aclanthology.org/2026.acl-long.2030/)

## RAG, hybrid RAG, or training?

Retrieval is a justified starting hypothesis. LaMP evaluates personalization across seven tasks including tweet paraphrasing, with user and time splits, and examines lexical/semantic/time-aware retrieval. Its results support testing selective historical examples instead of assuming the entire corpus must enter a prompt. Its task metrics do not establish authentic executive voice or a universally best retrieval algorithm. [Salemi et al., ACL 2024](https://aclanthology.org/2024.acl-long.399/)

For this repository, use the existing hybrid retrieval as an experiment arm. Do not train a model merely because it is available: first establish a real held-out corpus and show which recurring errors a prompt/profile/retrieval approach cannot fix. Fine-tuning becomes an experiment when there are enough varied approved brief→draft or edit pairs and a repeatable realization target. Treat preference optimization and automatic learning from edits as later work: a user's edit can change facts or strategy, not merely style.

## Enhancement implemented in this revision

**Explicit comment context and reply intent now accompany the existing generator.** This contributes a missing task capability beyond adding more surface scalar counts.

The API carries the following optional fields through a typed, sealed context into generation and revoice prompts:

- `content_kind`: `original_post` or `comment`; default original post for backwards compatibility.
- `parent_post`: the actual text being answered; required for comments.
- `reply_intent`: add perspective, ask a question, respectfully disagree, acknowledge, or answer.
- `supplied_points`: what the user wants to contribute; reuse the existing topic/angle field if practical.

Generation should first identify the addressed proposition from the provided parent text, then realize the selected intent using the voice examples. Parent-post claims remain attributed to the parent author; they do not become the executive's experiences, evidence, or agreement. Keep the requested reply stance and user-supplied facts fixed. A concise `acknowledgment → contribution → optional question` structure is one selectable plan, not a compulsory template for every comment.

This can be shipped with visible source/intent inputs, validation, prompt separation, and a small paired regression set without pretending a semantic analyzer has been scientifically calibrated. Evaluate against the existing generator on identical parent posts and intents; human reviewers judge relevance, stance preservation, distinctiveness, and editing time. It is a research-informed product hypothesis, not a claim that the papers validated this precise implementation.

If implementation scope is strictly the analysis subsystem, the next candidate is a separately versioned POS/dependency analyzer with an injected parser port and explicit statistical confidence, initially limited to a small set of clause and syntactic-relation rates. Do not present it as deterministic Tier 1 or claim it eliminates topic confounds.

## Primary reading list

1. [Alhafni et al. (2024), Personalized Text Generation with Fine-Grained Linguistic Control](https://aclanthology.org/2024.personalize-1.8/) — lexical, grammar, discourse control; read methods §§2.3–2.5 and data-size analysis §4.3.
2. [Altakrori et al. (2021), The Topic Confusion Task](https://aclanthology.org/2021.findings-emnlp.359/) — topic-swapping evaluation; read features §5 and experiments §§6–7.
3. [Wang et al. (2023), Can Authorship Representation Learning Capture Stylistic Features?](https://aclanthology.org/2023.tacl-1.80/) — content masking/paraphrase probes; read §§5–8 and limitations.
4. [Wegmann and Nguyen (2021), Does It Capture STEL?](https://aclanthology.org/2021.emnlp-main.569/) — content-controlled style comparisons; read task construction and limitations.
5. [Danescu-Niculescu-Mizil et al. (2013), A computational approach to politeness with application to social factors](https://aclanthology.org/P13-1025/) — contextual lexical/syntactic pragmatics; read §§2–4 and Table 3.
6. [Mir et al. (2019), Evaluating Style Transfer for Text](https://aclanthology.org/N19-1049/) — separate quality dimensions, human comparison; read §§2–5.
7. [Salemi et al. (2024), LaMP: When Large Language Models Meet Personalization](https://aclanthology.org/2024.acl-long.399/) — personalized retrieval and time/user splits; read task definitions and retrieval approach.
8. [Jangra et al. (2025), Evaluating Style-Personalized Text Generation: Challenges and Directions](https://arxiv.org/abs/2508.06374) — preprint; metric disagreement and short-reference limits; read §§2–4 and limitations.
9. [Baumler et al. (2026), Can You Make It Sound Like You?](https://aclanthology.org/2026.acl-long.2030/) — human post-editing and metric/perception divergence; read procedure, conclusions, and limitations.


## What the recovered deployment actually contains

The original deployed bundles were recovered byte for byte before updating Vercel. Ali has 62
posts (39 X, 23 LinkedIn; 3,811 words in aggregate analytics), and Matei has 84 (45 X, 39 LinkedIn;
4,584 words). All 146 lack exact publication dates. These are operator-transcribed public posts,
not a verified chronological sample. They remain development artifacts.

The current core feature aggregates give useful descriptive hypotheses:

| Existing core measurement | Ali sample | Matei sample | Interpretation limit |
|---|---:|---:|---|
| Mean sentence words, averaged per document | 14.23 | 16.88 | Mixed platform composition; not an identity test |
| Posts with a first-person opening | 50.0% | 27.4% | English marker proxy, not a semantic personal-disclosure measure |
| Mean first-person plural word ratio | 3.0% | 1.7% | Topic and source selection can affect this |
| Mean blank-line count | 0.65 | 0.44 | Transcription may alter formatting |

Do not turn these numbers into rigid instructions or significance claims. The richer platform
residuals remain visible in the app's profile analytics. The current data cannot justify a
chronological holdout, calibrated author identity, or a causal claim about engagement.

The engineering assignment's 100 suggested handles are stored as discovery seeds, with their
original supplied labels. A seed is not an acquired post or an engagement dataset. Public authored
essays collected for a third leader are supplementary writing and are not mislabeled as social
posts. Independent social references and human review still determine the acceptance gate.
