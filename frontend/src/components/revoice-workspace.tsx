"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

export function RevoiceWorkspace() {
  const sessionId = useSearchParams().get("session") ?? "";
  const workflow = useQuery({
    queryKey: ["workflow", sessionId],
    queryFn: () => api.workflow(sessionId),
    enabled: Boolean(sessionId),
  });
  const [edited, setEdited] = useState("");
  useEffect(() => {
    if (workflow.data && !edited) {
      const walkthroughEdit = sessionStorage.getItem(`ceo-voice-edit:${sessionId}`);
      setEdited(workflow.data.edited_content ?? walkthroughEdit ?? workflow.data.content);
    }
  }, [workflow.data, edited, sessionId]);
  const restoration = useMutation({
    mutationFn: (content: string) => api.revoice(sessionId, content),
    onSuccess: () => toast.success("Edit validated through the protected Re-Voice pipeline."),
    onError: (error) => toast.error(error.message),
  });

  if (!sessionId) return <Empty message="Generate a draft first, then continue here to edit and Re-Voice it." />;
  if (workflow.isPending) return <div className="space-y-4"><Skeleton className="h-64 w-full" /><Skeleton className="h-12 w-1/3" /></div>;
  if (workflow.isError || !workflow.data) return <Empty message="This workflow session is unavailable. Generate a new draft to continue." />;

  const original = workflow.data.content;
  const result = restoration.data?.revoiced_content ?? edited;
  const compared = compareLines(edited, result);
  return (
    <div>
      <p className="mb-8 border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">{workflow.data.disclaimer}</p>
      <div className="grid gap-8 lg:grid-cols-2">
        <Editor label="Generated" readOnly value={original} />
        <Editor label="Human edit" value={edited} onChange={setEdited} />
      </div>
      <div className="flex flex-col items-center py-10">
        <Button disabled={restoration.isPending || edited === original} onClick={() => restoration.mutate(edited)} size="lg">
          {restoration.isPending ? "Protecting intent…" : "Re-Voice"}
        </Button>
        <ArrowDown className="mt-6 h-4 w-4 text-muted-foreground" />
      </div>
      <section aria-live="polite" className="border-t border-border pt-10">
        <div className="flex items-end justify-between gap-4"><div><p className="eyebrow">Comparison</p><h2 className="mt-4 font-display text-3xl font-medium tracking-tight">Protected meaning. Traceable decisions.</h2></div><span className="font-mono text-xs text-muted-foreground">{restoration.data?.changed_regions.length ?? 0} engine changes</span></div>
        <div className="mt-8 whitespace-pre-wrap border-y border-border py-8 font-display text-lg leading-8 sm:text-xl">{compared.map((line, index) => <span className={line.changed ? "rounded-sm bg-primary/10" : undefined} key={`${index}-${line.text}`}>{line.text}{index < compared.length - 1 ? "\n" : ""}</span>)}</div>
        {restoration.data ? <div className="mt-8 border-t border-border">
          <ReportSection title="Re-Voice report"><p>Validation passed. Confidence: {Math.round((restoration.data.revoice_confidence ?? 0) * 100)}%. The deterministic local adapter proposed no unsupported rewrite.</p></ReportSection>
          <ReportSection title="Protected regions"><p>{restoration.data.preserved.length ? restoration.data.preserved.join(", ") : "Structure and user-authored regions remained inside the deterministic preservation envelope."}</p></ReportSection>
          <div className="pt-8"><Link className={buttonStyles()} href={`/evaluation?session=${sessionId}`}>Evaluate this draft</Link></div>
        </div> : null}
      </section>
    </div>
  );
}

function Empty({ message }: { message: string }) { return <div className="border-y border-border py-16 text-center"><p className="text-muted-foreground">{message}</p><Link className={buttonStyles({ variant: "secondary", className: "mt-6" })} href="/generate">Open Generate</Link></div>; }
function Editor({ label, value, readOnly = false, onChange }: { label: string; value: string; readOnly?: boolean; onChange?: (value: string) => void }) { return <label className="block"><span className="mb-3 flex justify-between text-sm font-medium">{label}<span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{readOnly ? "Protected source" : "Human editable"}</span></span><Textarea className="min-h-[32rem] font-display text-base leading-7" onChange={onChange ? (event) => onChange(event.target.value) : undefined} readOnly={readOnly} value={value} /></label>; }
function compareLines(before: string, after: string) { const lines = before.split("\n"); return after.split("\n").map((text, index) => ({ text, changed: text !== lines[index] })); }
