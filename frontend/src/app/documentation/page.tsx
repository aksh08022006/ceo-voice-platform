import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { CodeBlock } from "@/components/ui/code-block";

export const metadata: Metadata = {
  title: "Documentation",
  description: "A plain-language guide to the CEO Voice Platform workflow and design decisions.",
};

const sections = [
  "The product",
  "Why it is different",
  "Complete workflow",
  "Three core components",
  "One request",
  "Human review",
  "Trust boundary",
  "Research and parameters",
];

const workflow = [
  ["Ingestion", "Turn public source material into clean, traceable documents without flattening writing style."],
  ["Voice analysis", "Measure lexical, structural, rhetorical, tonal, and platform-specific patterns."],
  ["HVM voice profile", "Store those patterns as evidence-backed features, not a paragraph summary."],
  ["Profile Builder", "Validate and publish an immutable, inspectable profile release."],
  ["Context Compiler", "Translate the idea, identity, platform, policies, and active releases into targets."],
  ["Retrieval", "Select only the voice evidence and structural guidance needed for this request."],
  ["Generation", "Build the prompt last, call the configured model, validate the draft, and create a report."],
  ["Re-Voice", "Restore voice after a human edit while protecting meaning, order, facts, and formatting."],
  ["Evaluation", "Score voice, structure, platform fit, readability, constraints, and evidence use."],
];

export default function DocumentationPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-4xl border-b border-border pb-14">
        <p className="eyebrow">Documentation</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          The complete system, in plain language.
        </h1>
        <p className="mt-7 max-w-2xl text-lg leading-8 text-muted-foreground">
          The platform learns how a leader communicates, keeps voice separate from high-performing
          structure, and explains the evidence behind every draft.
        </p>
      </header>

      <div className="grid gap-14 lg:grid-cols-[12rem_minmax(0,52rem)] lg:gap-20">
        <nav aria-label="Documentation sections" className="lg:sticky lg:top-24 lg:self-start">
          <ul className="space-y-3 text-sm text-muted-foreground">
            {sections.map((section, index) => (
              <li key={section}>
                <a className="transition-colors hover:text-foreground" href={`#section-${index + 1}`}>
                  {section}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <article className="space-y-20">
          <DocSection id="section-1" eyebrow="01 · The product" title="What does it do?">
            <p>
              A user chooses a leader, chooses X or LinkedIn, and describes an idea and narrative
              angle. The system returns a platform-ready draft plus a report showing what voice
              patterns, structural patterns, and source evidence influenced it.
            </p>
          </DocSection>

          <DocSection id="section-2" eyebrow="02 · Why it is different" title="A voice profile is not a prompt summary.">
            <p>
              Ordinary voice cloning retrieves old posts and asks a model to imitate them. This
              platform first measures the leader&apos;s recurring micro-patterns and stores them in a
              structured HVM: the Hierarchical Voice Model. High-performing post structure lives
              separately in the VKR: the Virality Knowledge Representation. Voice stays dominant;
              structure is a subtle, independent influence.
            </p>
            <p className="mt-5">
              The model prompt is therefore the final compiled artifact—not the product&apos;s source of
              truth.
            </p>
          </DocSection>

          <DocSection id="section-3" eyebrow="03 · Complete workflow" title="From public evidence to an evaluated draft.">
            <Image
              alt="Public content flows through ingestion, analysis, HVM, profile publication, context compilation, retrieval, generation, Re-Voice, and evaluation. Independent VKR structure joins at context compilation."
              className="mt-8 w-full border-y border-border dark:invert"
              height={380}
              src="/architecture.svg"
              width={1800}
            />
            <ol className="mt-10 divide-y divide-border border-y border-border">
              {workflow.map(([name, explanation], index) => (
                <li className="grid gap-2 py-5 sm:grid-cols-[2rem_10rem_1fr]" key={name}>
                  <span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                  <strong className="font-medium text-foreground">{name}</strong>
                  <span>{explanation}</span>
                </li>
              ))}
            </ol>
          </DocSection>

          <DocSection id="section-4" eyebrow="04 · Three core components" title="The assignment boundaries remain visible.">
            <dl className="mt-8 divide-y divide-border border-y border-border">
              <Definition term="Voice Profile Engine">
                Builds the leader-specific HVM from their public corpus. It captures vocabulary,
                sentence and paragraph shape, rhetorical habits, tone, and platform differences,
                with confidence and evidence attached.
              </Definition>
              <Definition term="Virality Structure Library">
                Builds the independent VKR from performance-oriented examples. It describes hooks,
                pacing, post shapes, and calls to action without claiming those patterns belong to
                the leader.
              </Definition>
              <Definition term="Draft Generator">
                Combines one request-specific voice target and one subtle structure target. It can
                consume only the compact Retrieval Bundle, never entire profiles or raw corpora.
              </Definition>
            </dl>
          </DocSection>

          <DocSection id="section-5" eyebrow="05 · One request" title="Three inputs. One accountable result.">
            <CodeBlock className="mt-7">{`1. CEO identity\n2. Platform: X or LinkedIn\n3. Idea / angle`}</CodeBlock>
            <p className="mt-6">
              Internally, the platform pins the active releases, compiles the request, retrieves a
              bounded evidence bundle, builds the prompt, calls the configured provider, validates
              the response, and records model, latency, token, evidence, feature, and constraint
              details in the Generation Report.
            </p>
            <Link className="mt-6 inline-block font-medium text-primary underline-offset-4 hover:underline" href="/generate">
              Try the generation workflow
            </Link>
          </DocSection>

          <DocSection id="section-6" eyebrow="06 · Human review" title="Editing is part of the product workflow.">
            <p>
              Generate creates the first draft. A human then makes strategic or factual edits.
              Re-Voice compares the edited text with the latest accepted revision and may strengthen voice only in
              safe regions. It protects meaning, paragraph order, argument structure, facts, links,
              formatting, calls to action, and thread boundaries. Evaluation then explains the
              quality and remaining risks.
            </p>
            <p className="mt-5">
              Repeat the edit and revoice cycle as needed. Encrypted continuation snapshots keep the
              same profile and evidence available across server restarts. They remain in this browser
              tab for up to seven days after the latest successful step; copy drafts before closing the tab.
              This is a single-editor workflow without a shared team revision history.
            </p>
          </DocSection>

          <DocSection id="section-8" eyebrow="08 · Research and parameters" title="Voice is a pattern of choices in context.">
            <p>
              Stylometry, personalized generation, and pragmatics research give us testable ways to
              represent writing. The current engine measures 55 surface features across 11 analyzers.
              Grammar and semantic intent need separately validated annotation; adding more features
              alone does not establish recognizable voice.
            </p>
            <dl className="mt-8 divide-y divide-border border-y border-border">
              <Definition term="Vocabulary">Function words, contractions, recurring expressions, vocabulary diversity, and technical language. Separate characteristic wording from company and product names.</Definition>
              <Definition term="Rhythm and shape">Sentence-length distributions, paragraph breaks, punctuation, lists, and the positions of questions. Model a range of choices rather than forcing one average.</Definition>
              <Definition term="Grammar">Clause structure, tense, active and passive constructions, and syntactic depth. These remain proposed parser-based measurements, beyond the current surface rules.</Definition>
              <Definition term="Discourse and rhetoric">How claims, reasons, examples, concessions, analogies, and stories are ordered. Visible markers are clues; full rhetorical labels require contextual review.</Definition>
              <Definition term="Commitment and attribution">Who makes a claim, how certain it is, and what supports it. Rewriting should preserve facts, uncertainty, and the user&apos;s chosen position.</Definition>
              <Definition term="Replies">The parent post, addressed point, and chosen intent: answer, acknowledge, ask, add perspective, or disagree. Parent claims stay attributed to their author.</Definition>
              <Definition term="Platform and evidence">Compare X with X, LinkedIn with LinkedIn, and comments with comments. Keep spoken transcripts supplementary; they cannot establish a person&apos;s written formatting habits.</Definition>
            </dl>
            <p className="mt-6">
              We use retrieval as an experiment, with baseline, lexical, and hybrid alternatives.
              A topic match can masquerade as a voice match. Hold out independent examples, compare
              the same factual brief across voices, and score meaning preservation and naturalness
              separately. Fine-tuning is justified only by measured errors and sufficient approved examples.
            </p>
            <ul className="mt-6 space-y-3 text-sm">
              <li><a className="text-primary underline underline-offset-4" href="https://aclanthology.org/2024.personalize-1.8/">Alhafni et al. (2024): fine-grained linguistic control</a></li>
              <li><a className="text-primary underline underline-offset-4" href="https://aclanthology.org/2024.acl-long.399/">LaMP (2024): retrieval for personalized generation</a></li>
              <li><a className="text-primary underline underline-offset-4" href="https://aclanthology.org/2021.findings-emnlp.359/">Altakrori et al. (2021): separating author and topic signals</a></li>
              <li><a className="text-primary underline underline-offset-4" href="https://aclanthology.org/P13-1025/">Danescu-Niculescu-Mizil et al. (2013): politeness depends on context</a></li>
              <li><a className="text-primary underline underline-offset-4" href="https://aclanthology.org/N19-1049/">Mir et al. (2019): style, content preservation, and naturalness</a></li>
            </ul>
            <p className="mt-6">
              These papers inform our design; they do not validate this deployment. The assignment
              gate remains pending until Ali, Matei, and a third leader each have ten reviewed examples
              and averages of at least 4/5 for voice accuracy, post quality, and naturalness, alongside
              the separate reference-based model evaluation.
            </p>
          </DocSection>

          <DocSection id="section-7" eyebrow="07 · Trust boundary" title="A working profile is not an identity guarantee.">
            <p>
              The local Ali Ghodsi and Matei Zaharia development profiles are built from
              operator-transcribed public posts. They exercise the full pipeline, but incomplete
              source provenance, timestamps, reuse authority, and independent fidelity review mean
              they are not production identity claims. Human review remains required before use.
            </p>
            <p className="mt-5">
              The system also treats engagement patterns as associations, not proof that a format
              causes virality. Missing evidence, incompatible platforms, unsupported features, and
              conflicting constraints fail closed before the provider call.
            </p>
          </DocSection>
        </article>
      </div>
    </div>
  );
}

function DocSection({
  id,
  eyebrow,
  title,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="scroll-mt-24" id={id}>
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-4 font-display text-3xl font-medium tracking-[-0.035em] sm:text-4xl">{title}</h2>
      <div className="mt-5 text-base leading-8 text-muted-foreground">{children}</div>
    </section>
  );
}

function Definition({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-2 py-6 sm:grid-cols-[12rem_1fr]">
      <dt className="font-medium text-foreground">{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}
