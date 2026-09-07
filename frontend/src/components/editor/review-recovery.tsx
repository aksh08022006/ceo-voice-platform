"use client";

import { Button } from "@/components/ui/button";
import type { DraftReviewGate } from "@/lib/editor-types";

export function ReviewRecovery({ review, canEdit, pending, error, onRetryReview, onRegenerate }: { review: DraftReviewGate; canEdit: boolean; pending: boolean; error: string | null; onRetryReview: () => void; onRegenerate: () => void }) {
  const remaining = Math.max(0, review.regeneration_attempts_remaining);
  return <section className="border-t border-border pt-6" aria-label="Review next steps" aria-busy={pending}>
    {error ? <p className="mb-4 text-sm text-destructive" role="alert">{error}</p> : null}
    <div className="flex flex-wrap gap-3">
      {(review.state === "unavailable" || review.state === "review_pending") ? <Button variant="secondary" onClick={onRetryReview} disabled={pending || !canEdit}>{pending ? "Retrying review…" : review.state === "review_pending" ? "Run claim review" : "Retry claim review"}</Button> : null}
      {review.state === "blocked" && review.claims.some((claim) => claim.state !== "supported") ? <Button variant="secondary" onClick={onRegenerate} disabled={!canEdit || pending || remaining === 0}>{pending ? "Revising draft…" : "Revise flagged claims"}</Button> : null}
    </div>
    {review.state === "blocked" && review.claims.some((claim) => claim.state !== "supported") ? <p className="mt-3 text-xs leading-5 text-muted-foreground">{remaining > 0 ? `${remaining} ${remaining === 1 ? "attempt" : "attempts"} remaining for this brief. You can also edit the wording or add source evidence.` : "Automatic attempts are used up. Edit the wording or update the source brief before continuing."} A new version requires a fresh review.</p> : null}
  </section>;
}
