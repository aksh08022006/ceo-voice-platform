# Product walkthrough and recording script

Use this guide to record a clear 4–5 minute product walkthrough. The story is simple: **measure
voice, keep structure separate, retrieve only what one request needs, generate, preserve human
edits, and evaluate the result.**

## Before recording

From the repository root:

```bash
git pull origin main
make setup
make frontend-setup
cp .env.example .env
make doctor
make check-all
```

If you are using the development Ali and Matei corpora, build them with `make profiles` and point
the ignored `.env.local` catalog setting at the published development catalog as described in the
[README](../README.md#build-the-reviewed-ali-and-matei-corpora). Configure a model API key only in
an ignored local environment file; never show it in the recording.

Start the two processes in separate terminals:

```bash
make api
```

```bash
make frontend-dev
```

Confirm the product at `http://127.0.0.1:3000` and the health endpoint at
`http://127.0.0.1:8000/api/v1/health`. Use a clean browser window at 100% zoom. Keep terminals and
secrets out of the video after startup.

## Recording sequence

### 0:00–0:35 — The problem

**Screen:** Landing page.

**Say:**

> Most voice systems retrieve a few old posts and turn them into a short prompt such as “use short
> sentences and an informal tone.” That captures surface style, not the micro-patterns that make a
> leader recognizable. This platform models those patterns as evidence-backed knowledge and keeps
> every generation decision traceable.

### 0:35–1:15 — The design

**Screen:** Scroll to the single architecture diagram, then open Documentation.

**Say:**

> Public content is cleaned without flattening style. The analysis layer measures vocabulary,
> sentence and paragraph shape, rhetorical habits, tone, and platform differences. Those
> observations become an immutable HVM voice profile. Separately, the VKR captures useful content
> structures such as hooks and pacing. Voice and virality never become the same thing. They meet
> only when a specific request is compiled.

Briefly follow the chart from Ingestion to Evaluation. Emphasize: **the prompt is built last**.

### 1:15–2:25 — Generate from exactly three inputs

**Screen:** Generate.

1. Select Ali Ghodsi or Matei Zaharia.
2. Select LinkedIn or X.
3. Enter one clear idea and narrative angle.
4. Generate the draft.
5. Expand the Generation Report.

**Say:**

> These are the only product inputs required by the assignment: identity, platform, and idea or
> angle. Internally, the system pins the published HVM and VKR releases, compiles the request,
> retrieves only the minimum relevant evidence, renders the prompt, calls the configured model,
> validates the output, and records the result.

Point to voice features, structural features, evidence, model, latency, validation, and the
execution timeline. Explain that every retrieved item has a selection reason and evidence source.

### 2:25–3:10 — Human edit and Re-Voice

**Screen:** Edit the draft, then move to Re-Voice.

Make one strategic edit—change a fact, reorder wording inside a paragraph, or refine the call to
action—without rewriting everything.

**Say:**

> The expected workflow includes a human editor. Re-Voice compares the generated and edited drafts,
> detects protected regions, and attempts to restore style within those boundaries. It protects
> unchanged lines, formatting, recognized factual anchors, calls to action, and thread boundaries.
> The editor still reviews meaning and intent: lexical preservation cannot prove semantic equivalence.

Run Re-Voice and show the comparison plus the report: what changed, what stayed protected, which
voice features were targeted, and confidence.

### 3:10–3:45 — Independent evaluation

**Screen:** Evaluation.

**Say:**

> Evaluation is separate from generation. It scores voice, structure, platform compliance,
> readability, constraints, and evidence use independently. Hard deterministic failures cannot be
> hidden by a high average or by an LLM judge.

Show the overall disposition, one dimension, one constraint result, and one evidence trace.

### 3:45–4:20 — Profiles and benchmarks

**Screen:** Profiles, then Benchmarks.

**Say:**

> A profile page exposes its status, corpus summary, representation, and governance boundary.
> Releases are immutable and inspectable. The benchmark page verifies routing and regression
> behavior with synthetic cases; it does not claim real-person fidelity. A valid fidelity study
> requires held-out writing, blind human ratings, baselines, agreement statistics, and confidence
> intervals.

### 4:20–4:45 — Close

**Screen:** Return to the architecture diagram.

**Say:**

> The core engineering decision is separation: source data, measured voice, structural guidance,
> retrieval, model generation, human editing, and evaluation each have one responsibility. That
> makes the system explainable today and replaceable as it grows from two leaders to hundreds.

## Claims to use carefully

- Say **“built a structured voice profile from public content,”** not “trained a model on the CEO.”
- Say **“development profile,”** not “verified digital clone” or “production impersonation model.”
- Say **“operator-transcribed public posts,”** not “scraped through the LinkedIn or X API.”
- Say structural patterns **“are associated with engagement,”** not “cause virality.”
- A configured model API key changes the generation provider; it does not improve corpus authority.
- Generated content requires human review and must not be presented as endorsed by the named leader.

## Final recording checklist

- The architecture flow reads Ingestion → Analysis → HVM → Profile Builder → Context Compiler →
  Retrieval → Generation → Re-Voice → Evaluation.
- The VKR branch is visibly independent from voice.
- Generate shows only CEO, platform, and idea/angle.
- One complete session connects generation, edit, Re-Voice, and evaluation reports.
- No API key, environment file, private URL, or raw copyrighted corpus appears on screen.
- The development-profile disclosure and synthetic-benchmark disclosure are visible when discussed.
- Record at 1080p, 30 fps, with readable cursor movement and captions if narration is included.
