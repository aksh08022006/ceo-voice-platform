"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { DraftRevision, SavedDraftSummary } from "@/lib/editor-types";

import { reviewStateLabels } from "./review-status";

type DraftLibraryProps = {
  drafts: SavedDraftSummary[];
  loading: boolean;
  error: string | null;
  selectedDraftId: string | null;
  onSelect: (draftId: string) => void;
  onRetry: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
};

export function DraftLibrary({ drafts, loading, error, selectedDraftId, onSelect, onRetry, hasMore, loadingMore, onLoadMore }: DraftLibraryProps) {
  return <section aria-label="Saved drafts" aria-busy={loading}>
    <h2 className="font-display text-2xl font-medium">Saved drafts</h2>
    {loading ? <div className="mt-5 space-y-3"><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /></div> : null}
    {error ? <div className="mt-5"><p className="text-sm text-destructive" role="alert">{error}</p><Button className="mt-3" variant="secondary" size="sm" onClick={onRetry}>Retry loading drafts</Button></div> : null}
    {!loading && !error && drafts.length === 0 ? <p className="mt-5 text-sm leading-6 text-muted-foreground">Your saved drafts will appear here after the first generation.</p> : null}
    <ul className="mt-5 divide-y divide-border">{drafts.map((draft) => <li key={draft.id}>
      <button type="button" className="w-full rounded-sm py-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-current={selectedDraftId === draft.id ? "page" : undefined} onClick={() => onSelect(draft.id)}>
        <span className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">{draft.profile_name} · {draft.platform === "x" ? "X" : "LinkedIn"}</span><Badge>{reviewStateLabels[draft.review_state]}</Badge></span>
        <span className="mt-2 block text-sm font-medium leading-6">{draft.title}</span>
        <span className="mt-2 block text-xs text-muted-foreground">Version {draft.current_revision} · {draft.updated_by.display_name} · <time dateTime={draft.updated_at}>{formatTimestamp(draft.updated_at)}</time></span>
      </button>
    </li>)}</ul>
    {hasMore ? <Button className="mt-4 w-full" size="sm" variant="secondary" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? "Loading drafts…" : "Load more drafts"}</Button> : null}
  </section>;
}

export function RevisionHistory({ revisions, currentRevisionId, viewedRevisionId, onView, onRestore, restoring, hasMore, loadingMore, loadingError, onLoadMore }: { revisions: DraftRevision[]; currentRevisionId: string; viewedRevisionId: string; onView: (revisionId: string) => void; onRestore?: (revision: DraftRevision) => void; restoring: boolean; hasMore: boolean; loadingMore: boolean; loadingError: string | null; onLoadMore: () => void }) {
  const labels: Record<DraftRevision["kind"], string> = { generated: "Generated", human_edit: "Human edit", revoiced: "Voice revision", restored: "Restored as a new version" };
  return <section aria-label="Revision history">
    <h2 className="font-display text-xl font-medium">Version history</h2>
    <p className="mt-2 text-xs leading-5 text-muted-foreground">Earlier versions stay unchanged. Reusing one creates a new version that needs its own review.</p>
    <ol className="mt-4 divide-y divide-border">{revisions.map((revision) => <li className="py-4" key={revision.id}>
      <button className="w-full rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" type="button" onClick={() => onView(revision.id)} aria-pressed={viewedRevisionId === revision.id}>
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium">Version {revision.number}{currentRevisionId === revision.id ? <Badge>Current</Badge> : null}</span>
        <span className="mt-2 block text-xs text-muted-foreground">{labels[revision.kind]} · {revision.created_by.display_name}</span>
        <time className="mt-1 block text-xs text-muted-foreground" dateTime={revision.created_at}>{formatTimestamp(revision.created_at)}</time>
      </button>
      {viewedRevisionId === revision.id && currentRevisionId !== revision.id && onRestore ? <Button className="mt-3" size="sm" variant="secondary" disabled={restoring} onClick={() => onRestore(revision)}>{restoring ? "Creating version…" : "Use as a new version"}</Button> : null}
    </li>)}</ol>
    {loadingError ? <p className="mt-3 text-xs text-red-600 dark:text-red-400" role="alert">{loadingError}</p> : null}
    {hasMore ? <Button className="mt-4 w-full" size="sm" variant="secondary" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? "Loading history…" : loadingError ? "Retry older versions" : "Load older versions"}</Button> : null}
  </section>;
}

function formatTimestamp(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? "Time unavailable" : `${parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`; }
