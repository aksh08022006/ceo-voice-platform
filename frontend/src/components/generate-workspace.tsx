"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Copy } from "lucide-react";
import Link from "next/link";
import { useForm, useWatch } from "react-hook-form";
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
  content_kind: z.enum(["original_post", "comment"]),
  parent_post: z.string().max(8000),
  reply_intent: z.enum(["add_perspective", "ask_question", "respectfully_disagree", "acknowledge", "answer"]),
  content_type: z.enum(["post", "thread"]),
  thread_post_count: z.number().int().min(2).max(5),
  virality_influence: z.number().min(0).max(0.25),
  linkedin_length: z.enum(["standard", "profile"]),
  emotion: z.enum(["auto", "neutral", "enthusiastic", "grateful", "reflective", "curious", "concerned", "determined"]),
  intensity: z.enum(["restrained", "balanced", "expressive"]),
  warmth: z.enum(["profile", "reserved", "warm"]),
  emoji_policy: z.enum(["match_profile", "none", "one"]),
  viewpoint: z.string().max(600),
  rationale: z.string().max(600),
}).superRefine((value, context) => {
  if (value.content_kind === "comment" && !value.parent_post.trim()) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Paste the post you want to reply to.", path: ["parent_post"] });
  }
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
      content_kind: "original_post",
      parent_post: "",
      reply_intent: "add_perspective",
      content_type: "post",
      thread_post_count: 3,
      virality_influence: 0.12,
      linkedin_length: "standard",
      emotion: "auto", intensity: "balanced", warmth: "profile", emoji_policy: "match_profile",
      viewpoint: "", rationale: "",
    },
  });
  const platform = useWatch({ control: form.control, name: "platform" });
  const contentType = useWatch({ control: form.control, name: "content_type" });
  const contentKind = useWatch({ control: form.control, name: "content_kind" });
  const structureInfluence = useWatch({ control: form.control, name: "virality_influence" });
  const generation = useMutation({
    mutationFn: api.generate,
    onSuccess: () => toast.success("Draft ready for review."),
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(18rem,0.72fr)_minmax(0,1.28fr)] lg:gap-16">
      <form className="space-y-6" onSubmit={form.handleSubmit((value) => generation.mutate({
        profile_slug: value.profile_slug,
        platform: value.platform,
        idea: value.idea,
        expression: { emotion: value.emotion, intensity: value.intensity, warmth: value.warmth,
          emoji_policy: value.emoji_policy, viewpoint: value.viewpoint.trim() || undefined,
          rationale: value.rationale.trim() || undefined },
        content_kind: value.content_kind,
        parent_post: value.content_kind === "comment" ? value.parent_post : undefined,
        reply_intent: value.content_kind === "comment" ? value.reply_intent : undefined,
        content_type: value.content_kind === "original_post" && value.platform === "x" ? value.content_type : "post",
        thread_post_count: value.content_kind === "original_post" && value.platform === "x" && value.content_type === "thread" ? value.thread_post_count : undefined,
        virality_influence: value.virality_influence,
        minimum_words: value.content_kind === "original_post" && value.platform === "linkedin" && value.linkedin_length === "standard" ? 150 : undefined,
        maximum_words: value.content_kind === "original_post" && value.platform === "linkedin" && value.linkedin_length === "standard" ? 300 : undefined,
      }))}>
        <div className="rounded-lg border border-border p-4">
          <p className="text-sm font-medium">Start with an idea</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => {
              form.setValue("profile_slug", "ali-ghodsi"); form.setValue("platform", "linkedin");
              form.setValue("content_kind", "original_post"); form.setValue("content_type", "post");
              form.setValue("linkedin_length", "standard");
              form.setValue("idea", "Databricks just acquired Tabular, the company behind Apache Iceberg. The angle is that this validates the open-source approach to data infrastructure. The best technology wins when it is open, and this acquisition brings together the teams behind Spark and Iceberg under one roof.");
              form.setValue("emotion", "auto"); form.setValue("intensity", "balanced");
              form.setValue("warmth", "profile"); form.setValue("emoji_policy", "match_profile");
              form.setValue("viewpoint", ""); form.setValue("rationale", ""); form.setValue("virality_influence", 0.12);
            }}>Open infrastructure</Button>
            <Button type="button" variant="secondary" size="sm" onClick={() => {
              form.setValue("profile_slug", "matei-zaharia"); form.setValue("platform", "x");
              form.setValue("content_kind", "original_post"); form.setValue("content_type", "thread");
              form.setValue("thread_post_count", 3);
              form.setValue("idea", "The AI industry is converging on compound AI systems rather than monolithic models. The angle is that the next wave of AI progress will come from how you orchestrate multiple models, retrieval, and tools together, not from making a single model bigger. This is what Databricks has been building toward with Mosaic and their ML platform.");
              form.setValue("emotion", "auto"); form.setValue("intensity", "balanced");
              form.setValue("warmth", "profile"); form.setValue("emoji_policy", "match_profile");
              form.setValue("viewpoint", ""); form.setValue("rationale", ""); form.setValue("virality_influence", 0.12);
            }}>Compound AI</Button>
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">Choose a sample brief, or write your own below. Each sample sets the person and format for you.</p>
        </div>
        <Field label="CEO identity" error={form.formState.errors.profile_slug?.message}>
          <Select disabled={profiles.isPending} {...form.register("profile_slug")}>
            {profiles.data?.map((profile) => <option key={profile.slug} value={profile.slug}>{profile.name}</option>)}
          </Select>
        </Field>
        <Field label="Platform"><Select {...form.register("platform")}><option value="linkedin">LinkedIn</option><option value="x">X</option></Select></Field>
        <Field label={contentKind === "comment" ? "Your contribution / angle" : "Idea / angle"} error={form.formState.errors.idea?.message}><Textarea rows={8} placeholder={contentKind === "comment" ? "Describe the point you want to contribute, including your stance and any facts to preserve." : "Describe what the post is about and the narrative angle."} {...form.register("idea")} /></Field>
        <details className="border-y border-border py-4">
          <summary className="cursor-pointer text-sm font-medium">Emotion, emoji &amp; viewpoint</summary>
          <div className="mt-5 space-y-5">
          <p className="text-xs leading-5 text-muted-foreground">Start with this person’s writing habits. Set the intention for this post, then review that facts and claim strength remain faithful to your brief.</p>
            <Field label="Emotional register"><Select {...form.register("emotion")}>
              <option value="auto">Match the person and context</option><option value="neutral">Neutral / matter-of-fact</option>
              <option value="enthusiastic">Enthusiastic</option><option value="grateful">Grateful</option>
              <option value="reflective">Reflective</option><option value="curious">Curious</option>
              <option value="concerned">Concerned</option><option value="determined">Determined</option>
            </Select></Field>
            <Field label="Emotional intensity"><Select {...form.register("intensity")}><option value="restrained">Restrained</option><option value="balanced">Balanced</option><option value="expressive">Expressive</option></Select></Field>
            <Field label="Warmth"><Select {...form.register("warmth")}><option value="profile">Match the person</option><option value="reserved">Reserved</option><option value="warm">Warm</option></Select></Field>
            <Field label="Emoji use"><Select {...form.register("emoji_policy")}><option value="match_profile">Follow observed habits</option><option value="none">No emoji</option><option value="one">At most one, if appropriate</option></Select></Field>
            <Field label="Viewpoint to express" error={form.formState.errors.viewpoint?.message}><Textarea rows={3} maxLength={600} placeholder="Optional: Open infrastructure gives customers more choice. Preserve any qualifications." {...form.register("viewpoint")} /></Field>
            <Field label="Why this matters" error={form.formState.errors.rationale?.message}><Textarea rows={3} maxLength={600} placeholder="Optional: Explain the reasoning or value behind this post, using the facts you have supplied." {...form.register("rationale")} /></Field>
          </div>
        </details>
        <details className="border-y border-border py-4">
          <summary className="cursor-pointer text-sm font-medium">Format and structure</summary>
          <div className="mt-5 space-y-5">
            <Field label="Write a"><Select {...form.register("content_kind")}><option value="original_post">Post</option><option value="comment">Comment / reply</option></Select></Field>
            {contentKind === "comment" ? <>
              <Field label="Post you are replying to" error={form.formState.errors.parent_post?.message}><Textarea rows={5} placeholder="Paste the original post. Its claims remain attributed to its author." {...form.register("parent_post")} /></Field>
              <Field label="Reply intent"><Select {...form.register("reply_intent")}><option value="add_perspective">Add perspective</option><option value="ask_question">Ask a question</option><option value="respectfully_disagree">Respectfully disagree</option><option value="acknowledge">Acknowledge</option><option value="answer">Answer</option></Select></Field>
              <p className="text-xs leading-5 text-muted-foreground">{platform === "linkedin" ? "A concise reply of 40–100 words." : "A single reply within 280 characters."} Your chosen stance and supplied points guide the comment. Voice evidence currently comes from original posts.</p>
            </> : platform === "x" ? <>
              <Field label="X format"><Select {...form.register("content_type")}><option value="post">Single post</option><option value="thread">Thread</option></Select></Field>
              {contentType === "thread" ? <Field label="Posts in thread" error={form.formState.errors.thread_post_count?.message}><Select {...form.register("thread_post_count", { valueAsNumber: true })}>{[2, 3, 4, 5].map((count) => <option key={count} value={count}>{count} posts</option>)}</Select></Field> : null}
            </> : <Field label="LinkedIn length"><Select {...form.register("linkedin_length")}><option value="standard">150–300 words</option><option value="profile">Let the voice profile guide length</option></Select></Field>}
            <Field label={`Structural influence · ${Math.round(structureInfluence * 100)}%`} error={form.formState.errors.virality_influence?.message}>
              <input className="mt-1 w-full accent-primary" type="range" min="0" max="0.25" step="0.01" {...form.register("virality_influence", { valueAsNumber: true })} />
              <span className="mt-2 block text-xs font-normal leading-5 text-muted-foreground">A subtle 12% by default. Adjust how much structural guidance shapes the draft while preserving voice.</span>
            </Field>
          </div>
        </details>
        <Button disabled={generation.isPending || profiles.isError} size="lg" type="submit">
          {generation.isPending ? "Writing draft…" : "Generate draft"}<ArrowRight className="h-4 w-4" />
        </Button>
        {profiles.isError ? <p className="text-sm text-destructive">The writing service is unavailable. Please try again shortly.</p> : null}
      </form>

      <section aria-busy={generation.isPending} aria-live="polite">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div><p className="eyebrow">Generated draft</p><p className="mt-2 text-xs text-muted-foreground">{generation.data ? `${generation.data.platform} · ${generation.data.content_kind === "comment" ? "comment" : generation.data.content_type} · ${generation.data.profile_name}` : "Choose a person and describe your idea"}</p></div>
          {generation.data ? <Button size="icon" variant="ghost" onClick={() => { void navigator.clipboard.writeText(generation.data.content); toast.success("Draft copied."); }}><Copy className="h-4 w-4" /></Button> : null}
        </div>
        {generation.data && !generation.isPending && generation.data.initial_brief_review_status ? <div className="mt-5 border-s-2 border-primary bg-primary/5 p-4 text-sm leading-6">
          <p className="font-medium">{generation.data.initial_brief_review_status === "clear" ? "Brief check complete" : generation.data.initial_brief_review_status === "blocked" ? "Some sentences need your review" : "Brief check unavailable"}</p>
          <p className="mt-1 text-muted-foreground">{generation.data.initial_brief_review_status === "clear" ? "No unsupported statements were flagged by the model. Check the facts and voice before publishing." : generation.data.initial_brief_review_status === "blocked" ? "These statements need supporting facts or an edit." : "Your draft is available. Its factual consistency has not been checked."}</p>
          {generation.data.initial_brief_review_findings?.length ? <details className="mt-3"><summary className="cursor-pointer font-medium">Review {generation.data.initial_brief_review_findings.length} flagged sentence(s)</summary><ul className="mt-3 space-y-4">{generation.data.initial_brief_review_findings.map((finding, index) => <li key={index}><blockquote className="border-s-2 border-border ps-3">{finding.text}</blockquote><p className="mt-1 text-xs text-muted-foreground">{finding.reason}</p></li>)}</ul></details> : null}
        </div> : null}
        {generation.isPending ? <div className="space-y-4 py-10"><Skeleton className="h-5 w-4/5" /><Skeleton className="h-5 w-3/5" /><Skeleton className="mt-8 h-5 w-full" /></div> : (
          <article className="min-h-[30rem] whitespace-pre-wrap py-10 font-display text-xl leading-[1.65] tracking-[-0.015em] sm:text-2xl">
            {generation.data?.content ?? "Your generated draft and evidence report will appear here."}
          </article>
        )}
        {generation.data ? <>
          <p className="border-s-2 border-primary px-4 text-xs leading-5 text-muted-foreground">Draft for editorial review. Confirm facts, attribution, and personal details before publishing.</p>
          <div className="mt-8 border-t border-border">
            <ReportSection title="Generation report"><dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">{generation.data.report.map((item) => <Metric key={item.label} {...item} />)}</dl></ReportSection>
            {generation.data.thread.length > 1 ? <ReportSection title={`Thread · ${generation.data.thread.length} posts`}><ol className="space-y-5">{generation.data.thread.map((post, index) => <li className="border-s-2 border-border ps-4" key={`${index}-${post.slice(0, 16)}`}><span className="font-mono text-[10px] text-muted-foreground">{index + 1}/{generation.data.thread.length}</span><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{post}</p></li>)}</ol></ReportSection> : null}
            {generation.data.expression_profile ? <ReportSection title="Expression evidence">
              <p className="text-sm leading-6">{generation.data.expression_profile.document_count} distinct texts from this person on {generation.data.expression_profile.platform}. Emoji appeared in {generation.data.expression_profile.documents_with_emoji}; observed symbols: {generation.data.expression_profile.emoji_inventory.join(" ") || "none"}.</p>
              <p className="mt-3 text-xs leading-5 text-muted-foreground">These are visible writing cues, not measured emotions or inferred beliefs. Read the context, especially negation and quoted speech.</p>
              <ul className="mt-4 space-y-4">{generation.data.expression_profile.examples.map((example) => <li key={example.document_id}><p className="text-xs text-muted-foreground">{example.cues.map((cue) => cue.replaceAll("_", " ")).join(" · ")}</p><blockquote className="mt-2 border-s-2 border-border ps-3 text-sm leading-6">{example.text}</blockquote></li>)}</ul>
            </ReportSection> : null}
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
