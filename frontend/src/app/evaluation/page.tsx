import type { Metadata } from "next";

import { ReportSection } from "@/components/report-section";
import { Progress } from "@/components/ui/progress";

export const metadata: Metadata = { title: "Evaluation" };

const dimensions = [
  { label: "Voice", value: 94, detail: "Supported HVM features align with the selected evidence." },
  { label: "Structure", value: 96, detail: "The selected VKR arc and paragraph pacing are present." },
  { label: "Platform", value: 100, detail: "LinkedIn length and formatting constraints passed." },
  { label: "Readability", value: 89, detail: "Clear executive reading level with one dense paragraph." },
  { label: "Constraint", value: 100, detail: "All hard, negative, and user constraints passed." },
  { label: "Evidence", value: 86, detail: "Seven evidence units; one feature has moderate coverage." },
];

export default function EvaluationPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="grid gap-10 border-b border-border pb-16 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="max-w-3xl">
          <p className="eyebrow">Evaluation</p>
          <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
            Quality, without hiding the failure modes.
          </h1>
        </div>
        <div className="lg:text-right">
          <div className="font-display text-8xl font-medium tracking-[-0.07em] sm:text-9xl">92</div>
          <div className="mt-2 text-sm text-muted-foreground">Overall · Passed</div>
        </div>
      </header>

      <section className="py-16" aria-labelledby="dimension-heading">
        <h2 id="dimension-heading" className="sr-only">Evaluation dimensions</h2>
        <div className="space-y-9">
          {dimensions.map((dimension) => (
            <div className="grid gap-3 md:grid-cols-[10rem_1fr_3rem] md:items-center" key={dimension.label}>
              <span className="font-display text-lg font-medium">{dimension.label}</span>
              <div>
                <Progress value={dimension.value} />
                <p className="mt-2 text-xs leading-5 text-muted-foreground">{dimension.detail}</p>
              </div>
              <span className="font-mono text-sm md:text-right">{dimension.value}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-border">
        <ReportSection title="Blocking findings">
          <p>No platform, factual, protected-edit, or hard-constraint violations were found.</p>
        </ReportSection>
        <ReportSection title="Recommended improvement">
          <p>Split the third paragraph once to move readability from 89 toward the profile median.</p>
        </ReportSection>
        <ReportSection title="Evidence trace">
          <p>
            Evaluation report ev_0187 references HVM v4.2, VKR v2.6, retrieval bundle rb_89a2, and
            generation report gr_4107. The optional LLM judge was disabled.
          </p>
        </ReportSection>
      </section>
    </div>
  );
}
