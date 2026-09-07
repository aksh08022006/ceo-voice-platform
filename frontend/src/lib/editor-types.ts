/** View contracts for the authenticated editor. Identity and review gates come from the server. */

export type EditorActor = {
  id: string;
  display_name: string;
  email?: string;
  can_edit: boolean;
  can_approve: boolean;
};

export type EditorSource = {
  id: string;
  title: string;
  text: string;
  url: string | null;
  attribution: string | null;
};

export type EditorBrief = {
  id: string;
  content_sha256: string;
  idea: string;
  constraints: string[];
  sources: EditorSource[];
  parent_post: string | null;
  reply_intent: string | null;
};

export type DraftRevision = {
  id: string;
  number: number;
  parent_revision_id: string | null;
  content: string;
  content_sha256: string;
  brief_sha256: string;
  created_at: string;
  created_by: { id: string; display_name: string };
  kind: "generated" | "human_edit" | "revoiced" | "restored";
};

export type ReviewSpan = {
  start: number;
  end: number;
  text: string;
  offset_unit: "unicode_code_points";
};

export type ClaimState = "supported" | "unsupported" | "contradicted" | "uncertain";

export type ClaimCitation = {
  source_id: string;
  span: ReviewSpan;
};

export type ClaimResolution = {
  decision: "confirmed" | "requires_changes";
  note: string;
  reviewer: { id: string; display_name: string };
  reviewed_at: string;
  revision_id: string;
  content_sha256: string;
  review_run_id: string;
};

export type DraftClaim = {
  id: string;
  revision_id: string;
  span: ReviewSpan;
  state: ClaimState;
  reason: string;
  citations: ClaimCitation[];
  human_resolution: ClaimResolution | null;
};

export type ApprovalRecord = {
  reviewed_claim_ids: string[];
  id: string;
  revision_id: string;
  content_sha256: string;
  brief_sha256: string;
  review_run_id: string;
  reviewer: { id: string; display_name: string };
  note: string;
  approved_at: string;
};

export type ReviewGateState = "review_pending" | "unavailable" | "blocked" | "needs_review" | "approved";

export type DraftReviewGate = {
  state: ReviewGateState;
  review_run_id: string | null;
  revision_id: string;
  content_sha256: string;
  brief_sha256: string;
  can_approve: boolean;
  message: string;
  claims: DraftClaim[];
  regeneration_attempts_remaining: number;
  approval: ApprovalRecord | null;
};

export type SavedDraftSummary = {
  id: string;
  title: string;
  profile_name: string;
  platform: "x" | "linkedin";
  content_kind: "original_post" | "comment";
  current_revision: number;
  review_state: ReviewGateState;
  updated_at: string;
  updated_by: { id: string; display_name: string };
};

export type EditorDraft = {
  id: string;
  profile_slug: string;
  profile_name: string;
  platform: "x" | "linkedin";
  content_type: "post" | "thread";
  content_kind: "original_post" | "comment";
  thread_post_count: number | null;
  minimum_words?: number | null;
  maximum_words?: number | null;
  brief: EditorBrief;
  current_revision: DraftRevision;
  revisions: DraftRevision[];
  revisions_cursor: string | null;
  review: DraftReviewGate;
};

/** Server must bind approval to these exact values and obtain reviewer identity from auth. */
export type DraftApprovalRequest = {
  reviewed_claim_ids: string[];
  revision_id: string;
  content_sha256: string;
  brief_sha256: string;
  review_run_id: string;
  note: string;
};

export type DraftLibraryPage = { drafts: SavedDraftSummary[]; next_cursor: string | null };
export type RevisionHistoryPage = { revisions: DraftRevision[]; next_cursor: string | null };
