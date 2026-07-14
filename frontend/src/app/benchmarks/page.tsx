import type { Metadata } from "next";

import { Badge } from "@/components/ui/badge";
import { benchmarkRows } from "@/lib/demo-data";

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

      <div className="overflow-x-auto border-y border-border">
        <table className="w-full min-w-[680px] border-collapse text-left text-sm">
          <caption className="sr-only">Synthetic benchmark fixture results</caption>
          <thead>
            <tr className="border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-4 font-medium">Case label</th>
              <th className="px-3 py-4 font-medium">Platform</th>
              <th className="px-3 py-4 font-medium">Score</th>
              <th className="px-3 py-4 font-medium">Status</th>
              <th className="px-3 py-4 font-medium">Suite</th>
            </tr>
          </thead>
          <tbody>
            {benchmarkRows.map((row) => (
              <tr className="border-b border-border last:border-0" key={row.leader}>
                <td className="px-3 py-6 font-display text-lg font-medium">{row.leader}</td>
                <td className="px-3 py-6 text-muted-foreground">{row.platform}</td>
                <td className="px-3 py-6 font-mono">{row.score}</td>
                <td className="px-3 py-6"><Badge>{row.status}</Badge></td>
                <td className="px-3 py-6 font-mono text-xs text-muted-foreground">{row.suite}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="mt-20 grid gap-10 border-t border-border pt-10 md:grid-cols-3">
        <BenchmarkNote title="Baseline">Deterministic evaluator with the optional model judge disabled.</BenchmarkNote>
        <BenchmarkNote title="Expected warning">Tier-1 features cannot authorize real-person generation.</BenchmarkNote>
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
