import type { Metadata } from "next";

import { BenchmarkCases } from "@/components/benchmark-cases";

export const metadata: Metadata = { title: "Benchmarks" };

export default function BenchmarksPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-4xl">
        <p className="eyebrow">Benchmarks</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Repeatability before claims.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Fixed suites expose regressions across generation, Re-Voice, and evaluation. Scores retain
          their limitations instead of collapsing uncertainty into a single claim.
        </p>
      </header>

      <aside className="mb-10 border-s-2 border-primary px-5 py-1 text-sm leading-6 text-muted-foreground">
        These named cases are synthetic routing fixtures. They do not contain the leaders’ writing
        and do not measure real-person voice fidelity.
      </aside>

      <BenchmarkCases />

      <section className="mt-20 grid gap-10 border-t border-border pt-10 md:grid-cols-3">
        <BenchmarkNote title="Execution">Run each case from Generate; the API returns its sealed evaluation report.</BenchmarkNote>
        <BenchmarkNote title="No fabricated scores">The UI does not display a score until the backend evaluates a workflow.</BenchmarkNote>
        <BenchmarkNote title="Publishable study">Requires held-out corpora, human ratings, agreement, and confidence intervals.</BenchmarkNote>
      </section>
    </div>
  );
}

function BenchmarkNote({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="font-display text-lg font-medium">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{children}</p>
    </div>
  );
}
