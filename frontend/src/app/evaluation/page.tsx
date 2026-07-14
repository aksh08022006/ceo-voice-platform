"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export default function EvaluationPage() { return <Suspense fallback={<EvaluationSkeleton />}><EvaluationContent /></Suspense>; }

function EvaluationContent() {
  const session = useSearchParams().get("session") ?? "";
  const current = useQuery({ queryKey: ["workflow", session], queryFn: () => api.workflow(session), enabled: Boolean(session) });
  const evaluation = useMutation({ mutationFn: () => api.evaluate(session), onSuccess: () => toast.success("Evaluation completed."), onError: (error) => toast.error(error.message) });
  const data = evaluation.data ?? current.data;
  if (!session) return <Empty />;
  if (!data || current.isPending || evaluation.isPending) return <EvaluationSkeleton />;
  if (data.evaluation_score === null) return <div className="page-shell py-24"><p className="eyebrow">Evaluation</p><h1 className="balanced mt-5 max-w-3xl font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">Run the independent quality gate.</h1><p className="mt-6 max-w-2xl text-muted-foreground">The deterministic evaluator will inspect the sealed Re-Voice result, constraints, platform policy, and evidence trace.</p><Button className="mt-8" onClick={() => evaluation.mutate()} size="lg">Evaluate draft</Button></div>;
  return <div className="page-shell py-16 sm:py-24">
    <header className="grid gap-10 border-b border-border pb-16 lg:grid-cols-[1fr_auto] lg:items-end"><div className="max-w-3xl"><p className="eyebrow">Evaluation</p><h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">Quality, without hiding the failure modes.</h1></div><div className="lg:text-right"><div className="font-display text-8xl font-medium tracking-[-0.07em] sm:text-9xl">{Math.round(data.evaluation_score ?? 0)}</div><div className="mt-2 text-sm capitalize text-muted-foreground">Overall · {data.evaluation_status}</div></div></header>
    <p className="mt-8 border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">{data.disclaimer}</p>
    <section className="space-y-9 py-16">{data.dimensions.map((dimension) => <div className="grid gap-3 md:grid-cols-[12rem_1fr_3rem] md:items-center" key={dimension.label}><span className="font-display text-lg font-medium">{dimension.label}</span><div><Progress value={dimension.score} /><p className="mt-2 text-xs leading-5 text-muted-foreground">{dimension.summary}</p></div><span className="font-mono text-sm md:text-right">{Math.round(dimension.score)}</span></div>)}</section>
    <section className="border-t border-border"><ReportSection title="Recommended improvements"><p>{data.recommendations.length ? data.recommendations.join(" ") : "No deterministic improvement was required."}</p></ReportSection><ReportSection title="Evidence trace"><p>{data.evidence_count} evidence units evaluated against the sealed retrieval bundle. The optional LLM judge remained disabled.</p></ReportSection></section>
  </div>;
}

function Empty() { return <div className="page-shell py-24 text-center"><p className="text-muted-foreground">Complete Generate and Re-Voice to evaluate a sealed workflow.</p><Link className={buttonStyles({ className: "mt-6" })} href="/generate">Start a workflow</Link></div>; }
function EvaluationSkeleton() { return <div className="page-shell space-y-6 py-24"><Skeleton className="h-24 w-3/4" /><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-5/6" /></div>; }
