export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Profile = {
  slug: string;
  name: string;
  role: string;
  summary: string;
  status: string;
};

export type Evidence = {
  id: string;
  label: string;
  confidence: number;
  source: string;
  reason: string;
};

export type Dimension = {
  label: string;
  score: number;
  passed: boolean;
  summary: string;
};

export type Workflow = {
  session_id: string;
  profile_slug: string;
  profile_name: string;
  platform: string;
  content_type: "post" | "thread" | "announcement";
  virality_influence: number;
  thread: string[];
  content: string;
  edited_content: string | null;
  revoiced_content: string | null;
  report: { label: string; value: string }[];
  voice_features: Evidence[];
  structural_features: Evidence[];
  evidence_count: number;
  timeline: { label: string; value: string }[];
  changed_regions: string[];
  preserved: string[];
  revoice_confidence: number | null;
  evaluation_score: number | null;
  evaluation_status: string | null;
  dimensions: Dimension[];
  recommendations: string[];
  disclaimer: string;
};

export type Walkthrough = {
  slug: string;
  profile_slug: string;
  profile_name: string;
  title: string;
  platform: "linkedin" | "x";
  content_type: "post" | "thread" | "announcement";
  thread_post_count: number | null;
  virality_influence: number;
  minimum_words: number | null;
  maximum_words: number | null;
  idea: string;
  constraints: string;
  human_edit: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { message?: string; detail?: string } | null;
    throw new Error(body?.message ?? body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  profiles: () => request<Profile[]>("/api/v1/profiles"),
  walkthroughs: () => request<Walkthrough[]>("/api/v1/walkthroughs"),
  workflow: (id: string) => request<Workflow>(`/api/v1/workflows/${id}`),
  generate: (body: {
    profile_slug: string;
    platform: "linkedin" | "x";
    idea: string;
  }) => request<Workflow>("/api/v1/workflows/generate", { method: "POST", body: JSON.stringify(body) }),
  revoice: (id: string, content: string) =>
    request<Workflow>(`/api/v1/workflows/${id}/revoice`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  evaluate: (id: string) =>
    request<Workflow>(`/api/v1/workflows/${id}/evaluate`, { method: "POST" }),
};
