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
    onSuccess: (response) =>
      toast.success(
        response.revoice_applied
          ? "Voice restoration applied inside the protected edit envelope."
          : "Your edit was preserved because no safe voice-only rewrite was needed.",
      ),
    onError: (error) => toast.error(error.message),
  });

  if (!sessionId) return <Empty message="Generate a draft first, then continue here to edit and Re-Voice it." />;
  if (workflow.isPending) return <div className="space-y-4"><Skeleton className="h-64 w-full" /><Skeleton className="h-12 w-1/3" /></div>;
  if (workflow.isError || !workflow.data) return <Empty message="This workflow session is unavailable. Generate a new draft to continue." />;

  const original = workflow.data.content;
  const maximumCharacters = workflow.data.platform_maximum_characters;
  const editedCharacterCount = countCharacters(edited);
  const charactersOver = Math.max(0, editedCharacterCount - maximumCharacters);
  const exceedsPlatformLimit = charactersOver > 0;
  const result = restoration.data?.revoiced_content ?? edited;
  const compared = compareLines(edited, result);
  return (
    <div>
      <p className="mb-8 border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">{workflow.data.disclaimer}</p>
      <div className="grid gap-8 lg:grid-cols-2">
        <Editor label="Generated" readOnly value={original} />
        <Editor
          label="Human edit"
          maximumCharacters={maximumCharacters}
          value={edited}
          onChange={(value) => {
            restoration.reset();
            setEdited(value);
          }}
        />
      </div>
      <div className="flex flex-col items-center py-10">
        <Button
          disabled={restoration.isPending || edited === original || exceedsPlatformLimit}
          onClick={() => restoration.mutate(edited)}
          size="lg"
        >
          {restoration.isPending ? "Protecting intent…" : "Re-Voice"}
        </Button>
        {exceedsPlatformLimit ? (
          <p className="mt-4 max-w-md text-center text-xs leading-5 text-muted-foreground" role="alert">
            This {workflow.data.platform.toUpperCase()} edit is {charactersOver} characters over its
            {" "}{maximumCharacters}-character limit. Shorten the human edit before Re-Voice;
            protected text will not be deleted automatically.
          </p>
        ) : null}
        <ArrowDown className="mt-6 h-4 w-4 text-muted-foreground" />
      </div>
      <section aria-live="polite" className="border-t border-border pt-10">
        <div className="flex items-end justify-between gap-4"><div><p className="eyebrow">Comparison</p><h2 className="mt-4 font-display text-3xl font-medium tracking-tight">Protected meaning. Traceable decisions.</h2></div><span className="font-mono text-xs text-muted-foreground">{restoration.data?.changed_regions.length ?? 0} engine changes</span></div>
        <div className="mt-8 whitespace-pre-wrap border-y border-border py-8 font-display text-lg leading-8 sm:text-xl">{compared.map((line, index) => <span className={line.changed ? "rounded-sm bg-primary/10" : undefined} key={`${index}-${line.text}`}>{line.text}{index < compared.length - 1 ? "\n" : ""}</span>)}</div>
        {restoration.data ? <div className="mt-8 border-t border-border">
          <ReportSection title="Re-Voice report">
            <p>
              Validation passed. Restoration confidence:{" "}
              {Math.round((restoration.data.revoice_confidence ?? 0) * 100)}%.{" "}
              {restoration.data.revoice_applied
                ? `${restoration.data.changed_regions.length} editable region(s) were changed.`
                : restoration.data.revoice_fallback_used
                  ? `The provider made ${restoration.data.revoice_attempt_count ?? 0} unsafe proposal(s), so the valid human edit was preserved unchanged.`
                  : "No safe voice-only change was necessary; the human edit was preserved."}
            </p>
          </ReportSection>
          <ReportSection title="Protected regions"><p>{restoration.data.preserved.length ? restoration.data.preserved.join(", ") : "Structure and user-authored regions remained inside the deterministic preservation envelope."}</p></ReportSection>
          <div className="pt-8"><Link className={buttonStyles()} href={`/evaluation?session=${sessionId}`}>Evaluate this draft</Link></div>
        </div> : null}
      </section>
    </div>
  );
}

function Empty({ message }: { message: string }) { return <div className="border-y border-border py-16 text-center"><p className="text-muted-foreground">{message}</p><Link className={buttonStyles({ variant: "secondary", className: "mt-6" })} href="/generate">Open Generate</Link></div>; }
function Editor({ label, value, readOnly = false, maximumCharacters, onChange }: { label: string; value: string; readOnly?: boolean; maximumCharacters?: number; onChange?: (value: string) => void }) { const characterCount = countCharacters(value); const over = maximumCharacters !== undefined && characterCount > maximumCharacters; return <label className="block"><span className="mb-3 flex justify-between gap-4 text-sm font-medium">{label}<span className="flex gap-4 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><span>{readOnly ? "Protected source" : "Human editable"}</span>{maximumCharacters !== undefined ? <span className={over ? "font-semibold text-foreground" : undefined}>{characterCount} / {maximumCharacters}</span> : null}</span></span><Textarea aria-invalid={over} className="min-h-[32rem] font-display text-base leading-7" onChange={onChange ? (event) => onChange(event.target.value) : undefined} readOnly={readOnly} value={value} /></label>; }
function compareLines(before: string, after: string) { const lines = before.split("\n"); return after.split("\n").map((text, index) => ({ text, changed: text !== lines[index] })); }
function countCharacters(value: string) { return Array.from(value).length; }
