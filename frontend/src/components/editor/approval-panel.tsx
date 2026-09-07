"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { exactSpan } from "@/lib/editor-spans";
import type { DraftApprovalRequest, DraftReviewGate, DraftRevision, EditorActor, EditorBrief } from "@/lib/editor-types";

import { approvalMatchesRevision } from "./review-status";

type ApprovalPanelProps = {
  actor: EditorActor;
  brief: EditorBrief;
  revision: DraftRevision;
  review: DraftReviewGate;
  hasUnsavedChanges: boolean;
  onApprove: (request: DraftApprovalRequest) => Promise<void>;
};

export function ApprovalPanel(props: ApprovalPanelProps) {
  return <ApprovalForm {...props} key={`${props.revision.id}:${props.review.review_run_id}`} />;
}

function ApprovalForm({ actor, brief, revision, review, hasUnsavedChanges, onApprove }: ApprovalPanelProps) {
  const [confirmed, setConfirmed] = useState(false);
  const [checkedClaims, setCheckedClaims] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approved = approvalMatchesRevision(review, revision);
  const reviewMatches = review.revision_id === revision.id && review.content_sha256 === revision.content_sha256 && review.brief_sha256 === revision.brief_sha256 && brief.content_sha256 === revision.brief_sha256;
  const blockingClaims = review.claims.filter((claim) => claim.state === "unsupported" || claim.state === "contradicted");
  const unresolvedClaims = review.claims.filter((claim) => claim.state === "uncertain");
  const invalidLocations = review.claims.some((claim) => claim.revision_id !== revision.id || !exactSpan(revision.content, claim.span) || claim.citations.some((citation) => {
    const source = brief.sources.find((item) => item.id === citation.source_id);
    return !source || !exactSpan(source.text, citation.span);
  }));
  const allClaimsChecked = review.claims.length > 0 && review.claims.every((claim) => checkedClaims[claim.id]);
  const eligible = review.claims.length > 0 && actor.can_approve && review.can_approve && review.state === "needs_review" && reviewMatches && Boolean(review.review_run_id) && !hasUnsavedChanges && !blockingClaims.length && !unresolvedClaims.length && !invalidLocations;
  const unavailableReason = hasUnsavedChanges ? "Save your changes and review that version before approving."
    : !reviewMatches ? "Review the current draft and brief before approving."
    : review.state === "review_pending" ? "Run claim review for this saved version."
    : review.state === "unavailable" ? "Complete the claim review before approving."
    : blockingClaims.length ? "Correct unsupported or contradictory claims and run review again."
    : invalidLocations ? "Some claim or source excerpts do not match. Run review again."
    : unresolvedClaims.length ? "Correct uncertain claims or supply clearer evidence in a new brief, then run review again."
    : !actor.can_approve ? "An authorized reviewer must approve this draft."
    : !review.can_approve ? "This version is not ready for approval. Follow the review findings."
    : null;

  return <section className="border-t border-border pt-8" aria-label="Human approval">
    <h2 className="font-display text-2xl font-medium">Human approval</h2>
    {approved && review.approval && !hasUnsavedChanges ? <div className="mt-4 rounded-md border border-border p-5">
      <p className="text-sm font-medium">Version {revision.number} approved by {review.approval.reviewer.display_name}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{review.approval.note}</p>
      <p className="mt-3 text-xs text-muted-foreground">{review.approval.reviewed_claim_ids.length} claim acknowledgements recorded for this version. Any change to the text or brief requires a new review and approval.</p>
    </div> : <form className="mt-4 space-y-4" onSubmit={async (event) => {
      event.preventDefault();
      if (!eligible || !allClaimsChecked || !confirmed || note.trim().length < 20 || pending || !review.review_run_id) return;
      setPending(true);
      setError(null);
      try {
        await onApprove({ reviewed_claim_ids: review.claims.map((claim) => claim.id), revision_id: revision.id, content_sha256: revision.content_sha256, brief_sha256: revision.brief_sha256, review_run_id: review.review_run_id, note: note.trim() });
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Approval could not be saved. Your review note is still here; try again.");
      } finally { setPending(false); }
    }}>
      <p className="text-sm leading-6 text-muted-foreground">Approval is recorded as <span className="font-medium text-foreground">{actor.display_name}</span> for version {revision.number}. Automated scores do not replace this decision.</p>
      {unavailableReason ? <p className="text-sm leading-6" role="status">{unavailableReason}</p> : null}
      <fieldset className="space-y-3 rounded-lg border border-border p-4" disabled={!eligible || pending}>
        <legend className="px-2 text-sm font-medium">Check every claim against the source brief</legend>
        <p className="text-xs leading-6 text-muted-foreground">Read the source passages above. Check quantities, timing, attribution, uncertainty, and causal meaning yourself, even when the automated finding says support was found.</p>
        {review.claims.map((claim, index) => <label className="flex items-start gap-3 border-t border-border pt-3 text-sm leading-6" key={claim.id}><input className="mt-1 h-4 w-4 shrink-0 accent-primary" type="checkbox" checked={Boolean(checkedClaims[claim.id])} onChange={(event) => setCheckedClaims((current) => ({ ...current, [claim.id]: event.target.checked }))} /><span><span className="block text-xs text-muted-foreground">Claim {index + 1} · I checked this wording against the brief</span><span className="mt-1 block whitespace-pre-wrap">{claim.span.text}</span></span></label>)}
      </fieldset>
      <label className="block text-sm font-medium">Review note<Textarea className="mt-2 min-h-28" placeholder="Explain the evidence you checked and any wording that needed human judgment." value={note} onChange={(event) => setNote(event.target.value)} minLength={20} maxLength={2000} disabled={!eligible || pending} required /></label>
      <label className="flex items-start gap-3 text-sm leading-6"><input className="mt-1 h-4 w-4 accent-primary" type="checkbox" checked={confirmed} disabled={!eligible || pending} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed this exact draft against the brief and sources, including every claim finding.</label>
      {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
      <Button type="submit" disabled={!eligible || !allClaimsChecked || !confirmed || note.trim().length < 20 || pending}>{pending ? "Recording approval…" : `Approve version ${revision.number}`}</Button>
    </form>}
    <details className="mt-6 text-xs text-muted-foreground"><summary className="cursor-pointer">Review audit details</summary><dl className="mt-3 space-y-2 break-all"><div><dt className="font-medium">Version ID</dt><dd>{revision.id}</dd></div><div><dt className="font-medium">Text fingerprint</dt><dd>{revision.content_sha256}</dd></div><div><dt className="font-medium">Brief fingerprint</dt><dd>{revision.brief_sha256}</dd></div><div><dt className="font-medium">Review run</dt><dd>{review.review_run_id ?? "Not available"}</dd></div></dl></details>
  </section>;
}
