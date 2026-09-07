"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, type ReplyIntent } from "@/lib/api";
import { editorApi } from "@/lib/editor-api";
import type { EditorActor } from "@/lib/editor-types";

import { EditorAccessBoundary } from "./access-boundary";

type SourceInput = { key: string; title: string; text: string; url: string };

export function EditorGenerate() {
  return <EditorAccessBoundary>{(actor) => <NewDraftForm actor={actor} />}</EditorAccessBoundary>;
}

function NewDraftForm({ actor }: { actor: EditorActor }) {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles, retry: false });
  const router = useRouter();
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState("ali-ghodsi");
  const [platform, setPlatform] = useState<"linkedin" | "x">("linkedin");
  const [idea, setIdea] = useState("");
  const [kind, setKind] = useState<"original_post" | "comment">("original_post");
  const [parent, setParent] = useState("");
  const [intent, setIntent] = useState<ReplyIntent>("add_perspective");
  const [format, setFormat] = useState<"post" | "thread">("post");
  const [postCount, setPostCount] = useState(3);
  const [influence, setInfluence] = useState(0.12);
  const [constraints, setConstraints] = useState("");
  const [sources, setSources] = useState<SourceInput[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateSource(key: string, field: keyof Omit<SourceInput, "key">, value: string) {
    setSources((current) => current.map((source) => source.key === key ? { ...source, [field]: value } : source));
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !actor.can_edit) return;
    const rules = constraints.split("\n").map((line) => line.trim()).filter(Boolean);
    if (idea.trim().length < 20) { setError("Describe your idea in at least 20 characters."); return; }
    if (rules.length > 16 || rules.some((line) => line.length > 1000)) { setError("Use up to 16 constraints, with no more than 1,000 characters per line."); return; }
    if (sources.some((source) => !source.title.trim() || !source.text.trim())) { setError("Give each source a title and supporting text, or remove the empty source."); return; }
    if (sources.some((source) => source.url.trim() && !/^https?:\/\//i.test(source.url.trim()))) { setError("Source references must use an http:// or https:// URL."); return; }
    setPending(true);
    setError(null);
    try {
      const draft = await editorApi.generate({
        profile_slug: profile, platform, idea: idea.trim(), content_kind: kind,
        parent_post: kind === "comment" ? parent : undefined,
        reply_intent: kind === "comment" ? intent : undefined,
        content_type: platform === "x" && kind === "original_post" ? format : "post",
        thread_post_count: platform === "x" && kind === "original_post" && format === "thread" ? postCount : undefined,
        virality_influence: influence,
        minimum_words: platform === "linkedin" ? kind === "comment" ? 40 : 150 : undefined,
        maximum_words: platform === "linkedin" ? kind === "comment" ? 100 : 300 : undefined,
        constraints: rules,
        sources: sources.map(({ title, text, url }) => ({ title: title.trim(), text, url: url.trim() || undefined })),
      });
      queryClient.setQueryData(["editor", "draft", draft.id], draft);
      await queryClient.invalidateQueries({ queryKey: ["editor", "drafts"] });
      router.push(`/workspace?draft=${encodeURIComponent(draft.id)}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The draft could not be created. Your brief is still here; please try again.");
    } finally { setPending(false); }
  }

  if (!actor.can_edit) return <p className="text-sm leading-7 text-muted-foreground">Your workspace role can review saved drafts. An administrator can grant editing access.</p>;
  return <div className="grid gap-12 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,.7fr)]">
    <form className="space-y-6" onSubmit={generate} aria-busy={pending}>
      <fieldset className="space-y-6" disabled={pending}>
        <legend className="sr-only">Create a saved draft</legend>
        <label className="block text-sm font-medium" htmlFor="editor-profile">CEO identity<Select className="mt-2" disabled={profiles.isPending} id="editor-profile" onChange={(event) => setProfile(event.target.value)} required value={profile}>{profiles.data?.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</Select></label>
        {profiles.error ? <div role="alert"><p className="text-sm text-red-600">Profiles could not be loaded.</p><Button className="mt-2" onClick={() => profiles.refetch()} size="sm" variant="secondary">Retry loading profiles</Button></div> : null}
        <label className="block text-sm font-medium" htmlFor="editor-platform">Platform<Select className="mt-2" id="editor-platform" onChange={(event) => setPlatform(event.target.value as "linkedin" | "x")} value={platform}><option value="linkedin">LinkedIn</option><option value="x">X</option></Select></label>
        <label className="block text-sm font-medium" htmlFor="editor-idea">{kind === "comment" ? "Your contribution / angle" : "Idea / angle"}<Textarea className="mt-2 min-h-40" id="editor-idea" maxLength={1200} minLength={20} onChange={(event) => setIdea(event.target.value)} placeholder="What should this communicate? Include your stance and the facts that must stay intact." required value={idea} /></label>
        <details className="rounded-lg border border-border px-5 py-4"><summary className="cursor-pointer text-sm font-medium">Format and delivery</summary><div className="mt-5 space-y-5">
          <label className="block text-sm font-medium" htmlFor="editor-kind">Writing type<Select className="mt-2" id="editor-kind" onChange={(event) => setKind(event.target.value as "original_post" | "comment")} value={kind}><option value="original_post">Original post</option><option value="comment">Comment / reply</option></Select></label>
          {kind === "comment" ? <><label className="block text-sm font-medium" htmlFor="editor-parent">Post you are replying to<Textarea className="mt-2" id="editor-parent" maxLength={8000} onChange={(event) => setParent(event.target.value)} required value={parent} /></label><label className="block text-sm font-medium" htmlFor="editor-intent">Reply intent<Select className="mt-2" id="editor-intent" onChange={(event) => setIntent(event.target.value as ReplyIntent)} value={intent}><option value="add_perspective">Add perspective</option><option value="ask_question">Ask a question</option><option value="respectfully_disagree">Respectfully disagree</option><option value="acknowledge">Acknowledge</option><option value="answer">Answer</option></Select></label></> : null}
          {platform === "x" && kind === "original_post" ? <><label className="block text-sm font-medium" htmlFor="editor-format">Post format<Select className="mt-2" id="editor-format" onChange={(event) => setFormat(event.target.value as "post" | "thread")} value={format}><option value="post">Single post</option><option value="thread">Thread</option></Select></label>{format === "thread" ? <label className="block text-sm font-medium" htmlFor="editor-post-count">Posts in thread<Select className="mt-2" id="editor-post-count" onChange={(event) => setPostCount(Number(event.target.value))} value={postCount}>{[2, 3, 4, 5].map((count) => <option key={count} value={count}>{count}</option>)}</Select></label> : null}</> : null}
          <label className="block text-sm font-medium" htmlFor="editor-influence">Structure influence · {Math.round(influence * 100)}%<input className="mt-3 block w-full accent-primary" id="editor-influence" max={0.25} min={0} onChange={(event) => setInfluence(Number(event.target.value))} step={0.01} type="range" value={influence} /></label><p className="text-xs leading-5 text-muted-foreground">Optional patterns for openings and structure. This setting does not predict engagement.</p>
        </div></details>
        <details className="rounded-lg border border-border px-5 py-4"><summary className="cursor-pointer text-sm font-medium">Source evidence and constraints</summary><div className="mt-5 space-y-5"><p className="text-xs leading-6 text-muted-foreground">Paste factual evidence the reviewer can compare with the draft. A source URL is a reference label; its page is not fetched automatically.</p>
          <label className="block text-sm font-medium" htmlFor="editor-constraints">Constraints · one per line<Textarea className="mt-2" id="editor-constraints" maxLength={4000} onChange={(event) => setConstraints(event.target.value)} placeholder="For example: describe the rollout as planned, not already launched." value={constraints} /></label>
          {sources.map((source, index) => <section className="space-y-3 rounded-lg bg-surface p-4" key={source.key} aria-label={`Evidence source ${index + 1}`}><div className="flex items-center justify-between"><h3 className="text-sm font-medium">Evidence {index + 1}</h3><Button size="sm" variant="ghost" onClick={() => setSources((current) => current.filter((item) => item.key !== source.key))}>Remove</Button></div><label className="block text-xs font-medium" htmlFor={`source-title-${source.key}`}>Source title<Input className="mt-2" id={`source-title-${source.key}`} maxLength={160} onChange={(event) => updateSource(source.key, "title", event.target.value)} required value={source.title} /></label><label className="block text-xs font-medium" htmlFor={`source-text-${source.key}`}>Exact supporting text<Textarea className="mt-2" id={`source-text-${source.key}`} maxLength={4000} onChange={(event) => updateSource(source.key, "text", event.target.value)} required value={source.text} /></label><label className="block text-xs font-medium" htmlFor={`source-url-${source.key}`}>Reference URL · optional<Input className="mt-2" id={`source-url-${source.key}`} maxLength={2000} onChange={(event) => updateSource(source.key, "url", event.target.value)} type="url" value={source.url} /></label></section>)}
          <Button disabled={sources.length >= 3} onClick={() => setSources((current) => [...current, { key: crypto.randomUUID(), title: "", text: "", url: "" }])} size="sm" variant="secondary">Add source evidence</Button>
        </div></details>
      </fieldset>
      {error ? <p className="rounded-lg border border-red-500/30 p-4 text-sm leading-6 text-red-600 dark:text-red-400" role="alert">{error}</p> : null}
      <Button disabled={pending || profiles.isPending || !profiles.data?.length} type="submit">{pending ? "Generating and reviewing…" : "Generate saved draft"}</Button>
      {pending ? <p className="text-sm leading-6 text-muted-foreground" role="status">The draft will appear in your workspace when generation and claim review finish. A failed request can be retried without starting the same action twice.</p> : null}
    </form>
    <aside className="space-y-6 border-t border-border pt-6 lg:border-s lg:border-t-0 lg:ps-8 lg:pt-0"><h2 className="font-display text-2xl font-medium">From brief to approval</h2><ol className="list-decimal space-y-5 ps-5 text-sm leading-7 text-muted-foreground"><li>Generate from your idea and the selected voice profile.</li><li>Review exact claim passages against the supplied brief and evidence.</li><li>Edit the draft, save a new version, and rerun review.</li><li>An authorized reviewer approves the exact version before export.</li></ol><p className="text-xs leading-6 text-muted-foreground">Automated checks can miss meaning and voice errors. The reviewer reads the complete draft; diagnostic scores cannot approve it.</p></aside>
  </div>;
}
