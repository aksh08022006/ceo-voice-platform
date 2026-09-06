"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, type Workflow } from "@/lib/api";

const THREAD_SEPARATOR = "\n---\n";

export function RevoiceWorkspace() {
  const sessionId = useSearchParams().get("session") ?? "";
  const workflow = useQuery({
    queryKey: ["workflow", sessionId],
    queryFn: () => api.workflow(sessionId),
    enabled: Boolean(sessionId),
  });

  if (!sessionId) return <Empty message="Generate a draft first, then continue here to edit and Re-Voice it." />;
  if (workflow.isPending) return <div className="space-y-4"><Skeleton className="h-64 w-full" /><Skeleton className="h-12 w-1/3" /></div>;
  if (workflow.isError || !workflow.data) return <Empty message="This workflow session is unavailable. Generate a new draft to continue." />;
  return <RevisionEditor initialWorkflow={workflow.data} key={sessionId} />;
}

function RevisionEditor({ initialWorkflow }: { initialWorkflow: Workflow }) {
  const queryClient = useQueryClient();
  const [workflow, setWorkflow] = useState(initialWorkflow);
  const [edited, setEdited] = useState(() => {
    const savedEdit = typeof window === "undefined" ? null : sessionStorage.getItem(`ceo-voice-edit:${initialWorkflow.session_id}`);
    return initialWorkflow.revoiced_content ?? savedEdit ?? initialWorkflow.edited_content ?? initialWorkflow.content;
  });
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const restoration = useMutation({
    mutationFn: (revision: { content: string; expectedRevision: number }) =>
      api.revoice(workflow.session_id, revision.content, revision.expectedRevision),
    onSuccess: (response) => {
      setWorkflow(response);
      setEdited(response.revoiced_content ?? response.edited_content ?? response.content);
      queryClient.setQueryData(["workflow", response.session_id], response);
      sessionStorage.removeItem(`ceo-voice-edit:${response.session_id}`);
      toast.success(response.revoice_applied ? "Voice refined. This version is ready for your next edit." : "Your edit is preserved and ready for another pass.");
    },
    onError: (error) => toast.error(error.message),
  });

  const baseline = workflow.revoiced_content ?? workflow.content;
  const maximumCharacters = workflow.platform_maximum_characters;
  const editedPosts = edited.split(THREAD_SEPARATOR);
  const postCounts = editedPosts.map((post) => countCharacters(post.trim()));
  const maximumPosts = workflow.content_type === "thread" ? 5 : 1;
  const countError = editedPosts.length > maximumPosts || (workflow.content_type === "thread" && editedPosts.length < 2);
  const blankPost = postCounts.some((count) => count === 0);
  const overLimitPosts = postCounts.flatMap((count, index) => count > maximumCharacters ? [{ index, excess: count - maximumCharacters }] : []);
  const invalidEdit = countError || blankPost || overLimitPosts.length > 0;
  const result = restoration.data?.revoiced_content ?? edited;
  const compared = compareLines(restoration.variables?.content ?? edited, result);

  return (
    <div>
      <p className="mb-8 border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">{workflow.disclaimer}</p>
      {workflow.continuation_token ? <p className="mb-6 text-xs leading-5 text-muted-foreground">This draft can resume in this browser tab{workflow.continuation_expires_in_seconds ? ` for ${formatLifetime(workflow.continuation_expires_in_seconds)}` : " until this session expires"}. Copy the text before closing the tab.</p> : null}
      {workflow.content_kind === "comment" ? <details className="mb-6 border-y border-border py-4"><summary className="cursor-pointer text-sm">Reply context · {workflow.reply_intent?.replaceAll("_", " ")}</summary><blockquote className="mt-4 whitespace-pre-wrap border-s-2 border-border ps-4 text-sm text-muted-foreground">{workflow.parent_post}</blockquote><p className="mt-3 text-xs text-muted-foreground">Claims from the parent post stay attributed to its author. Each pass preserves your selected reply intent.</p></details> : null}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 text-sm">
        <p>{workflow.revision_count === 0 ? "First edit" : `Revision ${workflow.revision_count} · ready for another edit`}</p>
        <p className="text-xs text-muted-foreground">Your hook, paragraph order, and facts stay in place.</p>
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <Editor label={workflow.revision_count === 0 ? "Generated draft" : "Current accepted draft"} readOnly value={baseline} />
        <label className="block">
          <span className="mb-3 block text-sm font-medium">Human edit</span>
          <Textarea
            aria-describedby="edit-format-guidance"
            aria-invalid={invalidEdit}
            className="min-h-[32rem] font-display text-base leading-7"
            disabled={restoration.isPending}
            onChange={(event) => { restoration.reset(); setEdited(event.target.value); }}
            ref={editorRef}
            value={edited}
          />
          <span className="mt-3 block font-mono text-xs text-muted-foreground" id="edit-format-guidance">
            {workflow.content_type === "thread" ? "Separate posts with --- on its own line. " : ""}
            {postCounts.map((count, index) => `${postCounts.length > 1 ? `Post ${index + 1}: ` : ""}${count} / ${maximumCharacters}`).join(" · ")}
          </span>
        </label>
      </div>
      <div className="flex flex-col items-center py-10">
        <Button disabled={restoration.isPending || edited === baseline || invalidEdit} onClick={() => restoration.mutate({ content: edited, expectedRevision: workflow.revision_count })} size="lg">
          {restoration.isPending ? "Refining voice…" : "Re-Voice"}
        </Button>
        {invalidEdit ? <p className="mt-4 max-w-lg text-center text-xs leading-5 text-muted-foreground" role="alert">
          {countError ? (workflow.content_type === "thread" ? "Keep this X thread between 2 and 5 posts. " : "Keep this draft as one post. ") : ""}
          {blankPost ? "Each post needs some text. " : ""}
          {overLimitPosts.map(({ index, excess }) => `Post ${index + 1} is ${excess} characters over its ${maximumCharacters}-character limit. `).join("")}
        </p> : null}
        <ArrowDown className="mt-6 h-4 w-4 text-muted-foreground" />
      </div>
      <section aria-live="polite" className="border-t border-border pt-10">
        <div className="flex items-end justify-between gap-4"><div><p className="eyebrow">Comparison</p><h2 className="mt-4 font-display text-3xl font-medium tracking-tight">Your structure. A closer voice.</h2></div><span className="font-mono text-xs text-muted-foreground">{restoration.data?.changed_regions.length ?? 0} voice changes</span></div>
        <div className="mt-8 whitespace-pre-wrap border-y border-border py-8 font-display text-lg leading-8 sm:text-xl">{compared.map((line, index) => <span className={line.changed ? "rounded-sm bg-primary/10" : undefined} key={`${index}-${line.text}`}>{line.text}{index < compared.length - 1 ? "\n" : ""}</span>)}</div>
        {restoration.data ? <div className="mt-8 border-t border-border">
          <ReportSection title="Re-Voice report">
            <p>
              Structure validation passed. {restoration.data.revoice_applied
                ? `${restoration.data.changed_regions.length} edited region(s) received voice changes.`
                : restoration.data.revoice_fallback_used
                  ? "The model's proposed changes did not preserve your edit, so your version was kept."
                  : "The human edit was preserved without additional voice changes."}
            </p>
          </ReportSection>
          <ReportSection title="Preserved details"><p>{restoration.data.preserved.length ? restoration.data.preserved.join(", ") : "Paragraph order and the human edit were preserved."}</p></ReportSection>
          <div className="flex flex-wrap gap-4 pt-8">
            <Button variant="secondary" onClick={() => { restoration.reset(); editorRef.current?.focus(); }}>Edit this version again</Button>
            <Link className={buttonStyles()} href={`/evaluation?session=${workflow.session_id}`}>Evaluate this draft</Link>
          </div>
        </div> : null}
      </section>
    </div>
  );
}

function Empty({ message }: { message: string }) { return <div className="border-y border-border py-16 text-center"><p className="text-muted-foreground">{message}</p><Link className={buttonStyles({ variant: "secondary", className: "mt-6" })} href="/generate">Open Generate</Link></div>; }
function Editor({ label, value, readOnly = false }: { label: string; value: string; readOnly?: boolean }) { return <label className="block"><span className="mb-3 block text-sm font-medium">{label}</span><Textarea className="min-h-[32rem] font-display text-base leading-7" readOnly={readOnly} value={value} /></label>; }
function compareLines(before: string, after: string) { const lines = before.split("\n"); return after.split("\n").map((text, index) => ({ text, changed: text !== lines[index] })); }
function countCharacters(value: string) { return Array.from(value).length; }

function formatLifetime(seconds: number) { const days = seconds / 86400; if (Number.isInteger(days) && days >= 1) return `${days} ${days === 1 ? "day" : "days"}`; const hours = Math.floor(seconds / 3600); return hours >= 1 ? `${hours} ${hours === 1 ? "hour" : "hours"}` : `${Math.max(1, Math.floor(seconds / 60))} minutes`; }
