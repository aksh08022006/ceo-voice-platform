import { request, type ReplyIntent } from "./api";
import { createEditorMutation } from "./editor-mutation";
import type { DraftApprovalRequest, DraftLibraryPage, EditorActor, EditorDraft, RevisionHistoryPage } from "./editor-types";

export type EditorGenerateRequest = {
  profile_slug: string;
  platform: "linkedin" | "x";
  idea: string;
  content_kind: "original_post" | "comment";
  parent_post?: string;
  reply_intent?: ReplyIntent;
  content_type: "post" | "thread";
  thread_post_count?: number;
  virality_influence: number;
  minimum_words?: number;
  maximum_words?: number;
  constraints: string[];
  sources: { title: string; text: string; url?: string }[];
};

const base = "/api/v1/workspace";
const mutation = createEditorMutation(request);

export const editorApi = {
  session: () => request<EditorActor>(`${base}/session`),
  drafts: (cursor: string | null = null) => request<DraftLibraryPage>(`${base}/drafts?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  revisions: (id: string, cursor: string) => request<RevisionHistoryPage>(`${base}/drafts/${encodeURIComponent(id)}/revisions?limit=100&cursor=${encodeURIComponent(cursor)}`),
  draft: (id: string) => request<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}`),
  generate: (body: EditorGenerateRequest) => mutation<EditorDraft>(`${base}/drafts/generate`, body),
  edit: (id: string, expectedRevisionId: string, content: string) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/edit`, { expected_revision_id: expectedRevisionId, content }),
  revoice: (id: string, expectedRevisionId: string) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/revoice`, { expected_revision_id: expectedRevisionId }),
  review: (id: string, expectedRevisionId: string) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/review`, { expected_revision_id: expectedRevisionId }),
  regenerate: (id: string, expectedRevisionId: string) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/regenerate`, { expected_revision_id: expectedRevisionId }),
  restore: (id: string, expectedRevisionId: string, revisionId: string, revisionNumber: number) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/restore`, { expected_revision_id: expectedRevisionId, revision_id: revisionId, revision_number: revisionNumber }),
  approve: (id: string, body: DraftApprovalRequest) => mutation<EditorDraft>(`${base}/drafts/${encodeURIComponent(id)}/approve`, body),
  export: (id: string) => request<{ content: string; revision_id: string }>(`${base}/drafts/${encodeURIComponent(id)}/export`),
};
