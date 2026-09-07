import { Badge } from "@/components/ui/badge";
import type { DraftReviewGate, DraftRevision, ReviewGateState } from "@/lib/editor-types";

export const reviewStateLabels: Record<ReviewGateState, string> = {
  review_pending: "Review required",
  unavailable: "Review unavailable",
  blocked: "Changes required",
  needs_review: "Human review required",
  approved: "Approved",
};

export function approvalMatchesRevision(gate: DraftReviewGate, revision: DraftRevision): boolean {
  const approval = gate.approval;
  return gate.state === "approved" && gate.revision_id === revision.id && gate.content_sha256 === revision.content_sha256 && gate.brief_sha256 === revision.brief_sha256 && Boolean(
    approval &&
    Array.isArray(approval.reviewed_claim_ids) &&
    approval.reviewed_claim_ids.length === gate.claims.length &&
    new Set(approval.reviewed_claim_ids).size === gate.claims.length &&
    gate.claims.length > 0 &&
    gate.claims.every((claim) => claim.state === "supported" && approval.reviewed_claim_ids.includes(claim.id)) &&
    approval.note.trim().length >= 20 &&
    approval.revision_id === revision.id &&
    approval.content_sha256 === revision.content_sha256 &&
    approval.brief_sha256 === revision.brief_sha256 &&
    approval.review_run_id === gate.review_run_id,
  );
}

export function ReviewStatus({ gate, revision }: { gate: DraftReviewGate; revision: DraftRevision }) {
  const approved = approvalMatchesRevision(gate, revision);
  const stale = gate.revision_id !== revision.id || gate.content_sha256 !== revision.content_sha256 || gate.brief_sha256 !== revision.brief_sha256;
  const state = stale || (gate.state === "approved" && !approved) ? "needs_review" : gate.state;
  return <section aria-live="polite" className="border-y border-border py-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-display text-xl font-medium">Version {revision.number}</h2>
      <Badge>{reviewStateLabels[state]}</Badge>
    </div>
    <p className="mt-3 text-sm leading-6 text-muted-foreground">
      {stale ? "The text or brief changed. Review this version before approving it."
        : approved && gate.approval ? `Approved by ${gate.approval.reviewer.display_name} for this exact version.`
        : gate.state === "unavailable" ? "The review could not be completed. Approval stays unavailable until review succeeds."
        : gate.state === "review_pending" ? "Run claim review against the supplied brief and sources before approving this saved version."
        : gate.state === "blocked" ? "Unsupported, contradictory, or uncertain claims must be corrected before this version can be approved."
        : "Read the exact draft against the brief and record your approval."}
    </p>
    {gate.message ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{gate.message}</p> : null}
  </section>;
}
