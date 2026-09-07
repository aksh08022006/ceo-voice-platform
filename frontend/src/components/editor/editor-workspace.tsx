"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button, buttonStyles } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { editorApi } from "@/lib/editor-api";
import type { EditorActor, EditorDraft } from "@/lib/editor-types";

import { EditorAccessBoundary } from "./access-boundary";
import { DraftEditor } from "./draft-editor";
import { DraftLibrary } from "./draft-history";

export function EditorWorkspace() {
  return <EditorAccessBoundary>{(actor) => <WorkspaceContent actor={actor} />}</EditorAccessBoundary>;
}

function WorkspaceContent({ actor }: { actor: EditorActor }) {
  const search = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const selected = search.get("draft");
  const [unsaved, setUnsaved] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const library = useInfiniteQuery({
    queryKey: ["editor", "drafts"],
    queryFn: ({ pageParam }) => editorApi.drafts(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
  });
  const drafts = Array.from(new Map((library.data?.pages.flatMap((page) => page.drafts) ?? []).map((draft) => [draft.id, draft])).values());
  const active = useQuery({ queryKey: ["editor", "draft", selected], queryFn: () => editorApi.draft(selected!), enabled: Boolean(selected), retry: false, refetchOnWindowFocus: false });

  async function accept(promise: Promise<EditorDraft>) {
    const result = await promise;
    setUnsaved(false);
    setHistoryError(null);
    queryClient.setQueryData(["editor", "draft", result.id], result);
    await queryClient.invalidateQueries({ queryKey: ["editor", "drafts"] });
  }

  async function loadHistory() {
    const snapshot = active.data;
    if (!snapshot?.revisions_cursor || historyLoading) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const page = await editorApi.revisions(snapshot.id, snapshot.revisions_cursor);
      queryClient.setQueryData<EditorDraft>(["editor", "draft", snapshot.id], (current) => {
        if (!current || current.current_revision.id !== snapshot.current_revision.id || current.revisions_cursor !== snapshot.revisions_cursor) return current;
        return { ...current, revisions: Array.from(new Map([...current.revisions, ...page.revisions].map((revision) => [revision.id, revision])).values()), revisions_cursor: page.next_cursor };
      });
    } catch (failure) { setHistoryError(failure instanceof Error ? failure.message : "Older versions could not be loaded. Please try again."); }
    finally { setHistoryLoading(false); }
  }

  return <div className="grid items-start gap-10 lg:grid-cols-[16rem_minmax(0,1fr)] xl:gap-14">
    <aside className="max-h-96 space-y-8 overflow-y-auto lg:sticky lg:top-24 lg:max-h-[calc(100vh-8rem)]">
      {actor.can_edit ? <Link className={buttonStyles({ className: "w-full" })} href="/generate">New draft</Link> : <p className="text-sm text-muted-foreground">Signed in as {actor.display_name}</p>}
      <DraftLibrary drafts={drafts} hasMore={library.hasNextPage} loadingMore={library.isFetchingNextPage} onLoadMore={() => library.fetchNextPage()} error={library.error?.message ?? null} loading={library.isPending} onRetry={() => library.refetch()} onSelect={(id) => { if (id === selected) return; if (unsaved && !window.confirm("This draft has unsaved changes. Open another draft without saving?")) return; setUnsaved(false); setHistoryError(null); router.push(`/workspace?draft=${encodeURIComponent(id)}#editor`); }} selectedDraftId={selected} />
    </aside>
    <section className="min-w-0 scroll-mt-24" id="editor">
      {!selected ? <div className="border-y border-border py-12"><p className="section-label">Narrative Company</p><h1 className="mt-3 font-display text-4xl font-medium">Your publishing workspace</h1><p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">Create a draft, check its claims against the brief, and record a named approval before exporting. Each saved version stays in the history.</p><p className="mt-4 text-sm text-muted-foreground">Choose a saved draft to continue.</p></div> : null}
      {selected && active.isPending ? <div className="space-y-4" role="status"><p className="text-sm text-muted-foreground">Loading saved draft…</p><Skeleton className="h-96 w-full" /></div> : null}
      {active.error ? <div className="rounded-lg border border-border p-6"><p className="text-sm" role="alert">{active.error.message}</p><Button className="mt-4" variant="secondary" onClick={() => active.refetch()}>Retry loading draft</Button></div> : null}
      {active.data ? <DraftEditor key={`${active.data.id}:${reloadCount}`} actor={actor} draft={active.data} onUnsavedChange={setUnsaved} historyLoading={historyLoading} historyError={historyError} onLoadHistory={loadHistory} actions={{
        reload: async () => { await accept(editorApi.draft(active.data.id)); setReloadCount((count) => count + 1); },
        save: (content) => accept(editorApi.edit(active.data.id, active.data.current_revision.id, content)),
        revoice: () => accept(editorApi.revoice(active.data.id, active.data.current_revision.id)),
        retryReview: () => accept(editorApi.review(active.data.id, active.data.current_revision.id)),
        regenerate: () => accept(editorApi.regenerate(active.data.id, active.data.current_revision.id)),
        restore: (revision) => accept(editorApi.restore(active.data.id, active.data.current_revision.id, revision.id, revision.number)),
        approve: (body) => accept(editorApi.approve(active.data.id, body)),
        export: () => editorApi.export(active.data.id),
      }} /> : null}
    </section>
  </div>;
}
