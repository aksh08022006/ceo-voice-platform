import type { Metadata } from "next";

import { CodeBlock } from "@/components/ui/code-block";

export const metadata: Metadata = { title: "Documentation" };

const sections = ["Overview", "Knowledge releases", "Generation flow", "Onboarding", "Governance"];

export default function DocumentationPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-4xl border-b border-border pb-14">
        <p className="eyebrow">Documentation</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Understand every decision boundary.
        </h1>
      </header>

      <div className="grid gap-14 lg:grid-cols-[12rem_minmax(0,48rem)] lg:gap-20">
        <nav aria-label="Documentation sections" className="lg:sticky lg:top-24 lg:self-start">
          <ul className="space-y-3 text-sm text-muted-foreground">
            {sections.map((section, index) => (
              <li key={section}>
                <a className="hover:text-foreground" href={`#section-${index + 1}`}>{section}</a>
              </li>
            ))}
          </ul>
        </nav>

        <article className="space-y-20">
          <DocSection id="section-1" eyebrow="01 · Overview" title="Prompt-last by construction.">
            <p>
              Voice is a versioned, evidence-backed HVM. Reusable structure lives in an independent
              VKR. A request-specific compiler and deterministic retriever select the minimum
              authorized evidence before any prompt exists.
            </p>
          </DocSection>
          <DocSection id="section-2" eyebrow="02 · Knowledge releases" title="Immutable, inspectable, reversible.">
            <p>
              Every profile release pins its registry, observations, evidence, confidence,
              validation report, authority, and predecessor. Rollback resolves a prior release; it
              never mutates history.
            </p>
            <CodeBlock className="mt-6">{`HVM release v4.2\n├── 42 reviewed documents\n├── 68 evidence units\n├── 23 measured features\n└── authority: generation-approved`}</CodeBlock>
          </DocSection>
          <DocSection id="section-3" eyebrow="03 · Generation flow" title="Only the bundle reaches generation.">
            <ol className="mt-6 space-y-4 border-s border-border ps-6 text-sm">
              <li>Validate request, identity, platform, and exact active releases.</li>
              <li>Compile independent voice, structure, and constraint targets.</li>
              <li>Retrieve compact evidence with selection reasons and budgets.</li>
              <li>Render the prompt, call the provider, validate, and report.</li>
            </ol>
          </DocSection>
          <DocSection id="section-4" eyebrow="04 · Onboarding" title="New leaders are data, not code.">
            <CodeBlock className="mt-6">{`ceo-voice onboard \\\n+  --manifest onboarding.json \\\n+  --workspace ./data/runtime`}</CodeBlock>
            <p className="mt-5">
              Exit 0 means authorized. Exit 3 means both knowledge releases were published but the
              HVM remains descriptive and requires review.
            </p>
          </DocSection>
          <DocSection id="section-5" eyebrow="05 · Governance" title="Fail closed where confidence ends.">
            <p>
              The system never treats corpus volume as proof of authorship. Unsupported features,
              incompatible platforms, evidence gaps, conflicting constraints, or missing review
              stop generation before a provider call.
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
