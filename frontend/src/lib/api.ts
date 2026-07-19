export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Profile = {
  slug: string;
  name: string;
  role: string;
  summary: string;
  status: string;
};

export type CountBreakdown = {
  label: string;
  count: number;
};

export type FeatureMetric = {
  feature_id: string;
  version: string;
  display_name: string;
  dimension: string;
  value: number;
  unit: string;
  decision_state: string;
  confidence_coverage: number;
  support_count: number;
  platform: string | null;
  scope: "core" | "platform_residual";
};

export type FeatureComparison = {
  feature_id: string;
  display_name: string;
  dimension: string;
  unit: string;
  values: { profile_slug: string; profile_name: string; value: number }[];
};

export type ProfileAnalytics = {
  slug: string;
  name: string;
  role: string;
  summary: string;
  corpus: {
    corpus_hash: string;
    health_status: string;
    total_documents: number;
    successful_documents: number;
    partial_documents: number;
    failed_documents: number;
    reused_documents: number;
    observation_count: number;
    observed_feature_count: number;
    evidence_unit_count: number;
    total_characters: number;
    total_words: number;
    exact_publication_dates: number;
    missing_publication_dates: number;
    earliest_publication: string | null;
    latest_publication: string | null;
    build_eligible: boolean;
    generation_enabled_for_evaluation: boolean;
    failed_analyzers: number;
    platforms: CountBreakdown[];
    sources: CountBreakdown[];
    languages: CountBreakdown[];
    document_types: CountBreakdown[];
    content_types: CountBreakdown[];
    source_modalities: CountBreakdown[];
    acquisition_methods: CountBreakdown[];
    capture_media: CountBreakdown[];
    evidence_unit_types: CountBreakdown[];
    reposts: number;
    quote_posts: number;
    uncertain_documents: number;
    development_only_documents: number;
    issues: { code: string; message: string; blocking: boolean }[];
  };
  release: {
    release_id: string;
    version: number;
    status: string;
    artifact_status: string;
    authority: string;
    content_hash: string;
    previous_release_id: string | null;
    registry_version: string;
    registry_hash: string;
    compiler_version: string;
    validator_version: string;
    structurally_valid: boolean;
    validation_issue_count: number;
    lifecycle_event_count: number;
    created_at: string;
    published_at: string;
    inspected_at: string;
    summary: string;
  };
  dimensions: {
    dimension: string;
    core_feature_count: number;
    total_component_count: number;
    average_coverage: number;
    support_links: number;
  }[];
  features: FeatureMetric[];
  comparisons: FeatureComparison[];
  limitations: string[];
  evidence_count_explanation: string;
  hvm_formula: string;
  trust_statement: string;
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
  profileAnalytics: (slug: string) =>
    request<ProfileAnalytics>(`/api/v1/profiles/${slug}/analytics`),
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
