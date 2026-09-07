"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { redirect, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { AUTH_ENABLED } from "@/lib/auth/config";
import { api } from "@/lib/api";

const diagnosticLabels: Record<string, { label: string; description: string }> = {
  "Voice Fidelity": {
    label: "Measured style fit",
    description: "Numeric writing features, evidence coverage, and copying checks.",
  },
  "Structural Fidelity": {
    label: "Structure pattern match",
    description: "Detected formatting and rhetorical patterns compared with selected examples.",
  },
  "Constraint Compliance": {
    label: "Requested wording checks",
    description: "Only directly testable rules, such as required or prohibited wording, contribute.",
  },
  "Platform Compliance": {
    label: "Length and format checks",
    description: "Per-post character limits, thread shape, and output validation.",
  },
  "Factual Preservation": {
    label: "Factual anchor checks",
    description: "Recognized names, numbers, quotations, and links checked against the brief and evidence; complete claims are not verified.",
  },
  "Edit Preservation": {
    label: "Edit text checks",
    description: "Text and protected-region comparisons after Re-Voice; wording similarity does not establish preserved meaning.",
  },
  Readability: {
    label: "Sentence and spacing checks",
    description: "Sentence length, paragraph presence, and excessive blank lines.",
  },
};

export default function EvaluationPage() {
  if (AUTH_ENABLED) redirect("/workspace"); return <Suspense fallback={<EvaluationSkeleton />}><EvaluationContent /></Suspense>; }

function EvaluationContent() {
  const session = useSearchParams().get("session") ?? "";
  const current = useQuery({ queryKey: ["workflow", session], queryFn: () => api.workflow(session), enabled: Boolean(session) });
  const evaluation = useMutation({ mutationFn: () => api.evaluate(session), onSuccess: () => toast.success("Evaluation completed."), onError: (error) => toast.error(error.message) });
  const data = evaluation.data ?? current.data;
  if (!session) return <Empty />;
  if (current.isError) return <div className="page-shell py-24"><p role="alert">{current.error.message}</p><Link className={buttonStyles({ className: "mt-6" })} href="/generate">Start a new draft</Link></div>;
  if (!data || current.isPending || evaluation.isPending) return <EvaluationSkeleton />;
  if (data.evaluation_score === null) return <div className="page-shell py-24"><p className="eyebrow">Draft diagnostics</p><h1 className="balanced mt-5 max-w-3xl font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">Inspect this draft.</h1><p className="mt-6 max-w-2xl text-muted-foreground">Check measurable writing features, recognized factual anchors, editing constraints, and platform limits. These checks do not verify unsupported new claims, preserved meaning, or voice accuracy.</p><Button className="mt-8" onClick={() => evaluation.mutate()} size="lg">Run diagnostics</Button><ReviewGate /></div>;
  return <div className="page-shell py-16 sm:py-24">
    <header className="grid gap-10 border-b border-border pb-16 lg:grid-cols-[1fr_auto] lg:items-end"><div className="max-w-3xl"><p className="eyebrow">Draft diagnostics</p><h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">Measured fit and remaining work.</h1></div><div className="lg:text-right"><div className="font-display text-8xl font-medium tracking-[-0.07em] sm:text-9xl">{Math.round(data.evaluation_score ?? 0)}</div><div className="mt-2 text-sm capitalize text-muted-foreground">Diagnostic / 100 · {data.evaluation_status}</div></div></header>
    <p className="mt-8 border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">Review facts, attribution, and wording before publishing. Automated checks are one part of editorial review.</p>
    <p className="mt-6 max-w-3xl text-sm leading-6 text-muted-foreground">Scores cover observable text checks. They do not verify unsupported new claims, preserved meaning, or voice accuracy.</p>
    <section className="space-y-9 py-16">{data.dimensions.map((dimension) => <div className="grid gap-3 md:grid-cols-[12rem_1fr_3rem] md:items-center" key={dimension.label}><span className="font-display text-lg font-medium">{diagnosticLabels[dimension.label]?.label ?? dimension.label}</span><div><Progress value={dimension.score} /><p className="mt-2 text-xs leading-5 text-muted-foreground">{diagnosticLabels[dimension.label]?.description} {dimension.summary}</p></div><span className="font-mono text-sm md:text-right">{Math.round(dimension.score)}</span></div>)}</section>
    <section className="border-t border-border"><ReportSection title="Recommended improvements"><p>{data.recommendations.length ? data.recommendations.join(" ") : "No further changes were suggested by these checks."}</p></ReportSection><ReportSection title="Source summary"><p>{data.evidence_count} source excerpts informed these checks. A person should review the draft for voice and factual accuracy.</p></ReportSection></section>
    <ReviewGate />
  </div>;
}

function ReviewGate() {
  return <aside className="mt-12 max-w-3xl border-t border-border pt-8"><h2 className="font-display text-2xl">Before you publish</h2><p className="mt-3 text-sm leading-7 text-muted-foreground">Read the draft aloud for voice and naturalness. Verify factual claims and personal details, then check that it communicates the point you intended. Automated scores do not replace this review.</p><Link className="mt-4 inline-block text-sm text-primary underline underline-offset-4" href="/documentation#review">Read the review guide</Link></aside>;
}

function Empty() { return <div className="page-shell py-24 text-center"><p className="text-muted-foreground">Generate a draft to review its writing, format, and editing checks.</p><Link className={buttonStyles({ className: "mt-6" })} href="/generate">Start a draft</Link></div>; }
function EvaluationSkeleton() { return <div className="page-shell space-y-6 py-24"><Skeleton className="h-24 w-3/4" /><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-5/6" /></div>; }
