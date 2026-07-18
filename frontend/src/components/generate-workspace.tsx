"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Copy } from "lucide-react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, type Evidence } from "@/lib/api";

const schema = z.object({
  profile_slug: z.string().min(1, "Select a CEO profile."),
  platform: z.enum(["linkedin", "x"]),
  idea: z.string().min(20, "Describe the idea in at least 20 characters.").max(1200),
}).superRefine((value, context) => {
  const filler = new Set(["a", "am", "ceo", "cto", "draft", "hello", "hey", "hi", "i", "im", "make", "me", "post", "the", "write"]);
  const profileTerms = new Set(value.profile_slug.toLowerCase().split("-"));
  const ideaTerms = (value.idea.toLowerCase().match(/[\p{L}\p{N}'-]+/gu) ?? [])
    .map((term) => term.replace(/^['-]+|['-]+$/g, ""));
  if (!ideaTerms.some((term) => term && !filler.has(term) && !profileTerms.has(term))) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Describe what the post should communicate, not only the selected identity.",
      path: ["idea"],
    });
  }
});
type Form = z.infer<typeof schema>;

export function GenerateWorkspace() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const form = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      profile_slug: "ali-ghodsi",
      platform: "linkedin",
      idea: "",
    },
  });
  const generation = useMutation({
    mutationFn: api.generate,
    onSuccess: () => toast.success("Draft generated through the complete evidence pipeline."),
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(18rem,0.72fr)_minmax(0,1.28fr)] lg:gap-16">
      <form className="space-y-6" onSubmit={form.handleSubmit((value) => generation.mutate(value))}>
        <Field label="CEO identity" error={form.formState.errors.profile_slug?.message}>
          <Select disabled={profiles.isPending} {...form.register("profile_slug")}>
            {profiles.data?.map((profile) => <option key={profile.slug} value={profile.slug}>{profile.name} · {profile.status}</option>)}
          </Select>
        </Field>
        <Field label="Platform"><Select {...form.register("platform")}><option value="linkedin">LinkedIn</option><option value="x">X</option></Select></Field>
        <Field label="Idea / angle" error={form.formState.errors.idea?.message}><Textarea rows={8} placeholder="Describe what the post is about and the narrative angle." {...form.register("idea")} /></Field>
        <Button disabled={generation.isPending || profiles.isError} size="lg" type="submit">
          {generation.isPending ? "Running full pipeline…" : "Generate draft"}<ArrowRight className="h-4 w-4" />
        </Button>
        {profiles.isError ? <p className="text-sm text-destructive">Backend unavailable. Start the API on port 8000.</p> : null}
      </form>

      <section aria-busy={generation.isPending} aria-live="polite">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div><p className="eyebrow">Generated draft</p><p className="mt-2 text-xs text-muted-foreground">{generation.data ? `${generation.data.platform} · ${generation.data.content_type} · ${generation.data.profile_name}` : "Waiting for a governed request"}</p></div>
          {generation.data ? <Button size="icon" variant="ghost" onClick={() => { void navigator.clipboard.writeText(generation.data.content); toast.success("Draft copied."); }}><Copy className="h-4 w-4" /></Button> : null}
        </div>
        {generation.isPending ? <div className="space-y-4 py-10"><Skeleton className="h-5 w-4/5" /><Skeleton className="h-5 w-3/5" /><Skeleton className="mt-8 h-5 w-full" /></div> : (
          <article className="min-h-[30rem] whitespace-pre-wrap py-10 font-display text-xl leading-[1.65] tracking-[-0.015em] sm:text-2xl">
            {generation.data?.content ?? "Your generated draft and evidence report will appear here."}
          </article>
        )}
        {generation.data ? <>
          <p className="border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">{generation.data.disclaimer}</p>
          <div className="mt-8 border-t border-border">
            <ReportSection title="Generation report"><dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">{generation.data.report.map((item) => <Metric key={item.label} {...item} />)}</dl></ReportSection>
            {generation.data.thread.length > 1 ? <ReportSection title={`Thread · ${generation.data.thread.length} posts`}><ol className="space-y-5">{generation.data.thread.map((post, index) => <li className="border-s-2 border-border ps-4" key={`${index}-${post.slice(0, 16)}`}><span className="font-mono text-[10px] text-muted-foreground">{index + 1}/{generation.data.thread.length}</span><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{post}</p></li>)}</ol></ReportSection> : null}
            <ReportSection title="Voice evidence"><EvidenceList items={generation.data.voice_features} /></ReportSection>
            <ReportSection title="Structural evidence"><EvidenceList items={generation.data.structural_features} /></ReportSection>
            <ReportSection title="Execution timeline"><dl className="grid grid-cols-2 gap-4">{generation.data.timeline.map((item) => <Metric key={item.label} {...item} />)}</dl></ReportSection>
          </div>
          <div className="mt-8"><Link className={buttonStyles({ variant: "secondary" })} href={`/revoice?session=${generation.data.session_id}`}>Edit and Re-Voice</Link></div>
        </> : null}
      </section>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block text-sm font-medium"><span className="mb-2 block">{label}</span>{children}{error ? <span className="mt-2 block text-xs text-destructive">{error}</span> : null}</label>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div><dt className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt><dd className="mt-1 text-sm">{value}</dd></div>; }
function EvidenceList({ items }: { items: Evidence[] }) { return items.length ? <ul className="divide-y divide-border">{items.map((item) => <li className="py-3" key={item.id}><div className="flex justify-between gap-4"><span>{item.label}</span><span className="font-mono text-xs">{item.confidence.toFixed(2)}</span></div><p className="mt-1 text-xs text-muted-foreground">{item.reason}</p></li>)}</ul> : <p>No evidence in this category.</p>; }
