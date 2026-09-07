"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { DraftApprovalRequest, DraftRevision, EditorActor, EditorDraft } from "@/lib/editor-types";

import { ApprovalPanel } from "./approval-panel";
import { ClaimReviewPanel } from "./claim-review-panel";
import { RevisionHistory } from "./draft-history";
import { ReviewRecovery } from "./review-recovery";
import { approvalMatchesRevision, ReviewStatus } from "./review-status";

export type DraftEditorActions = {
  reload: () => Promise<void>;
  save: (content: string) => Promise<void>;
  revoice: () => Promise<void>;
  retryReview: () => Promise<void>;
  regenerate: () => Promise<void>;
  restore: (revision: DraftRevision) => Promise<void>;
  approve: (request: DraftApprovalRequest) => Promise<void>;
  export: () => Promise<{ content: string; revision_id: string }>;
};

export function DraftEditor(props: { actor: EditorActor; draft: EditorDraft; actions: DraftEditorActions; onUnsavedChange?: (dirty: boolean) => void; historyLoading: boolean; historyError: string | null; onLoadHistory: () => void }) {
  return <DraftEditorVersion {...props} key={props.draft.current_revision.id} />;
}

function DraftEditorVersion({ actor, draft, actions, onUnsavedChange, historyLoading, historyError, onLoadHistory }: { actor: EditorActor; draft: EditorDraft; actions: DraftEditorActions; onUnsavedChange?: (dirty: boolean) => void; historyLoading: boolean; historyError: string | null; onLoadHistory: () => void }) {
  const revision = draft.current_revision;
  const [content, setContent] = useState(revision.content);
  const [viewedRevisionId, setViewedRevisionId] = useState(revision.id);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const dirty = content !== revision.content;
  const posts = content.split("\n---\n");
  const characterLimit = draft.platform === "x" ? 280 : 3000;
  const expectedPosts = draft.content_type === "thread" ? draft.thread_post_count ?? 2 : 1;
  const wordCount = content.trim().split(/\s+/).filter(Boolean).length;
  const formatIssues = [
    ...(posts.length !== expectedPosts ? [`Keep ${expectedPosts} ${expectedPosts === 1 ? "post" : "posts"} in this draft.`] : []),
    ...posts.flatMap((post, index) => !post.trim() ? [`Post ${index + 1} is empty.`] : Array.from(post).length > characterLimit ? [`Post ${index + 1} exceeds ${characterLimit} characters.`] : []),
    ...(draft.minimum_words != null && wordCount < draft.minimum_words ? [`Use at least ${draft.minimum_words} words.`] : []),
    ...(draft.maximum_words != null && wordCount > draft.maximum_words ? [`Use no more than ${draft.maximum_words} words.`] : []),
  ];
  const viewedRevision = draft.revisions.find((item) => item.id === viewedRevisionId) ?? revision;
  const viewingHistory = viewedRevision.id !== revision.id;

  useEffect(() => {
    if (!dirty) return;
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    const warnBeforeNavigation = (event: MouseEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === "_blank" || anchor.href === window.location.href) return;
      if (!window.confirm("This draft has unsaved changes. Leave without saving?")) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    document.addEventListener("click", warnBeforeNavigation, true);
    return () => { window.removeEventListener("beforeunload", warnBeforeLeaving); document.removeEventListener("click", warnBeforeNavigation, true); };
  }, [dirty]);

  async function run(label: string, action: () => Promise<void>) {
    if (pending) return;
    setPending(label);
    setError(null);
    try { await action(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "This change could not be completed. Your text is still here; please try again."); }
    finally { setPending(null); }
  }

  async function copyApproved() {
    if (!approvalMatchesRevision(draft.review, revision) || dirty) return;
    try { const exported = await actions.export(); if (exported.revision_id !== revision.id || exported.content !== revision.content) throw new Error("The approved version changed. Reload this draft before exporting."); await navigator.clipboard.writeText(exported.content); setCopied(true); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "The approved draft could not be exported. Please try again."); }
  }

  return <div className="space-y-8">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="section-label">{draft.profile_name} · {draft.platform === "x" ? "X" : "LinkedIn"}</p><h1 className="mt-3 font-display text-3xl font-medium">Draft editor</h1><p className="mt-2 text-sm text-muted-foreground">Version {revision.number} saved by {revision.created_by.display_name}</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="ghost" disabled={Boolean(pending)} onClick={() => { if (dirty && !window.confirm("Discard your unsaved changes and reload the saved version?")) return; void run("reload", actions.reload); }}>{pending === "reload" ? "Reloading…" : "Reload saved version"}</Button><Button variant="secondary" disabled={!approvalMatchesRevision(draft.review, revision) || dirty || Boolean(pending)} onClick={copyApproved}>{copied ? "Copied approved text" : "Copy approved text"}</Button></div>
    </div>
    <ReviewStatus gate={draft.review} revision={revision} />
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_17rem]">
      <section aria-label="Edit draft" className="space-y-4">
        {viewingHistory ? <div className="rounded-lg border border-border bg-surface p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-sm font-medium">Version {viewedRevision.number} · Read only</h2><Button size="sm" variant="secondary" onClick={() => setViewedRevisionId(revision.id)}>Return to current version</Button></div><p className="mt-5 whitespace-pre-wrap text-sm leading-7">{viewedRevision.content}</p></div> : <><label className="block text-sm font-medium" htmlFor="saved-draft-content">Current draft</label><Textarea className="min-h-72 leading-7" disabled={!actor.can_edit || Boolean(pending)} id="saved-draft-content" maxLength={12000} onChange={(event) => { setContent(event.target.value); onUnsavedChange?.(event.target.value !== revision.content); }} value={content} /><p className="text-xs leading-6 text-muted-foreground">{posts.map((post, index) => `Post ${index + 1}: ${Array.from(post).length}/${characterLimit} characters`).join(" · ")} · {wordCount} words{draft.content_type === "thread" ? ". Separate posts with --- on its own line." : "."}</p>{formatIssues.length ? <p className="text-xs leading-6 text-red-600 dark:text-red-400">{formatIssues.join(" ")} You can save your progress; format must be corrected before approval.</p> : null}<div className="flex flex-wrap items-center gap-3"><Button disabled={!actor.can_edit || !dirty || !content.trim() || Boolean(pending)} onClick={() => run("save", () => actions.save(content))}>{pending === "save" ? "Saving…" : "Save changes"}</Button><Button variant="secondary" disabled={!actor.can_edit || dirty || Boolean(pending)} onClick={() => run("revoice", actions.revoice)}>{pending === "revoice" ? "Refining voice…" : "Refine voice"}</Button><span className="text-xs text-muted-foreground" role="status">{dirty ? "Unsaved changes · save to review this wording" : "Saved version · review below refers to this exact text"}</span></div></>}
        {error ? <p className="rounded-lg border border-red-500/30 p-4 text-sm text-red-600 dark:text-red-400" role="alert">{error}</p> : null}
        {dirty ? <p className="text-xs leading-5 text-muted-foreground">The review below applies to the saved text. Saving changes creates a new version and requires a fresh approval.</p> : null}
      </section>
      <RevisionHistory currentRevisionId={revision.id} onRestore={actor.can_edit && !dirty ? (id) => run("restore", () => actions.restore(id)) : undefined} onView={setViewedRevisionId} restoring={pending === "restore"} hasMore={Boolean(draft.revisions_cursor)} loadingMore={historyLoading} loadingError={historyError} onLoadMore={onLoadHistory} revisions={draft.revisions} viewedRevisionId={viewedRevisionId} />
    </div>
    <ClaimReviewPanel actor={actor} brief={draft.brief} review={draft.review} revision={revision} />
    <ReviewRecovery canEdit={actor.can_edit && !dirty} error={null} onRegenerate={() => run("regenerate", actions.regenerate)} onRetryReview={() => run("review", actions.retryReview)} pending={Boolean(pending)} review={draft.review} />
    <ApprovalPanel actor={actor} brief={draft.brief} hasUnsavedChanges={dirty || Boolean(pending)} onApprove={actions.approve} review={draft.review} revision={revision} />
  </div>;
}
