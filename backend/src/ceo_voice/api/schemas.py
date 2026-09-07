"""Stable browser-facing request and response contracts."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ceo_voice.models.communication import ReplyIntent
from ceo_voice.models.enums import ContentType, Platform
from ceo_voice.models.expression import ExpressionDirection, ExpressionProfile


class GenerateWorkflowRequest(BaseModel):
    """Three primary product inputs with bounded optional format controls."""

    model_config = ConfigDict(extra="forbid")

    profile_slug: str = Field(min_length=1)
    platform: Literal[Platform.X, Platform.LINKEDIN]
    idea: str = Field(min_length=20, max_length=1_200)
    content_kind: Literal["original_post", "comment"] = "original_post"
    parent_post: str | None = Field(default=None, min_length=1, max_length=8_000)
    reply_intent: ReplyIntent | None = None
    content_type: Literal[ContentType.POST, ContentType.THREAD] = ContentType.POST
    thread_post_count: int | None = Field(default=None, ge=2, le=5)
    virality_influence: float = Field(default=0.12, ge=0, le=0.25)
    minimum_words: int | None = Field(default=None, ge=1, le=2_000)
    maximum_words: int | None = Field(default=None, ge=1, le=2_000)
    expression: ExpressionDirection | None = None

    @model_validator(mode="after")
    def require_consistent_output_shape(self) -> "GenerateWorkflowRequest":
        if self.content_kind == "comment":
            if (
                self.parent_post is None
                or not self.parent_post.strip()
                or self.reply_intent is None
            ):
                raise ValueError("comments require the parent post and a reply intent")
            if self.content_type is not ContentType.POST:
                raise ValueError("comments are single posts, not threads")
            if self.platform is Platform.LINKEDIN:
                self.minimum_words = self.minimum_words if self.minimum_words is not None else 40
                self.maximum_words = self.maximum_words if self.maximum_words is not None else 100
        elif self.parent_post is not None or self.reply_intent is not None:
            raise ValueError("parent_post and reply_intent require comment output")
        if self.content_type is ContentType.THREAD:
            if self.platform is not Platform.X:
                raise ValueError("threads are supported only for X")
            if self.thread_post_count is None:
                raise ValueError("thread requests require a post count between 2 and 5")
        elif self.thread_post_count is not None:
            raise ValueError("thread_post_count requires thread output")
        if (
            self.minimum_words is not None
            and self.maximum_words is not None
            and self.minimum_words > self.maximum_words
        ):
            raise ValueError("minimum_words cannot exceed maximum_words")
        return self

    @model_validator(mode="after")
    def require_subject_beyond_identity(self) -> "GenerateWorkflowRequest":
        """Reject identity-only text that does not describe a post subject or angle."""

        filler = {
            "a",
            "am",
            "ceo",
            "cto",
            "draft",
            "hello",
            "hey",
            "hi",
            "i",
            "im",
            "make",
            "me",
            "post",
            "the",
            "write",
        }
        profile_terms = set(self.profile_slug.casefold().replace("-", " ").split())
        idea_terms = {
            token.casefold().strip("'-") for token in re.findall(r"[\w'-]+", self.idea, re.UNICODE)
        }
        if not idea_terms - filler - profile_terms:
            raise ValueError(
                "Describe what the post should communicate, not only the selected identity."
            )
        return self


class ReVoiceWorkflowRequest(BaseModel):
    """Human-edited draft submitted to the Re-Voice engine."""

    content: str = Field(min_length=1, max_length=20_000)
    editor_note: str | None = Field(default=None, max_length=1_000)
    expected_revision: int | None = Field(default=None, ge=0)
    continuation_token: str | None = Field(default=None, max_length=2_000_000)


class ContinueWorkflowRequest(BaseModel):
    continuation_token: str = Field(min_length=1, max_length=2_000_000)


class ReviewWorkflowTextRequest(ContinueWorkflowRequest):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=12_000)


class BriefReviewFinding(BaseModel):
    text: str
    verdict: str
    reason: str


class MetricResponse(BaseModel):
    label: str
    value: str


class EvidenceResponse(BaseModel):
    id: UUID
    label: str
    confidence: float
    source: str
    reason: str


class DimensionResponse(BaseModel):
    label: str
    score: float
    passed: bool
    summary: str


class WorkflowResponse(BaseModel):
    """Compact product projection of the sealed workflow session."""

    session_id: UUID
    expression: ExpressionDirection | None = None
    expression_profile: ExpressionProfile | None = None
    continuation_token: str | None = None
    continuation_expires_in_seconds: int | None = None
    revision_count: int = Field(default=0, ge=0)
    current_candidate_id: UUID
    profile_slug: str
    profile_name: str
    platform: str
    platform_maximum_characters: int = Field(ge=1)
    content_type: str
    content_kind: Literal["original_post", "comment"] = "original_post"
    parent_post: str | None = None
    reply_intent: ReplyIntent | None = None
    virality_influence: float
    thread: tuple[str, ...]
    content: str
    edited_content: str | None = None
    revoiced_content: str | None = None
    report: tuple[MetricResponse, ...]
    voice_features: tuple[EvidenceResponse, ...]
    structural_features: tuple[EvidenceResponse, ...]
    evidence_count: int
    timeline: tuple[MetricResponse, ...]
    changed_regions: tuple[str, ...] = ()
    preserved: tuple[str, ...] = ()
    revoice_confidence: float | None = None
    revoice_applied: bool | None = None
    revoice_fallback_used: bool | None = None
    revoice_attempt_count: int | None = Field(default=None, ge=0)
    generation_call_count: int = Field(default=0, ge=0)
    fidelity_call_count: int = Field(default=0, ge=0)
    initial_brief_review_status: str | None = None
    initial_brief_review_error: str | None = None
    initial_brief_review_findings: tuple[BriefReviewFinding, ...] = ()
    evaluation_score: float | None = None
    evaluation_status: str | None = None
    dimensions: tuple[DimensionResponse, ...] = ()
    recommendations: tuple[str, ...] = ()
    disclaimer: str


class ProfileResponse(BaseModel):
    slug: str
    name: str
    role: str
    summary: str
    status: str


class CountBreakdownResponse(BaseModel):
    """Named count used by corpus and evidence distributions."""

    label: str
    count: int = Field(ge=0)


class CorpusIssueResponse(BaseModel):
    """One explicit limitation detected for the published corpus."""

    code: str
    message: str
    blocking: bool


class CorpusAnalyticsResponse(BaseModel):
    """Evidence ledger for the exact corpus admitted to an HVM release."""

    corpus_hash: str
    health_status: str
    total_documents: int = Field(ge=1)
    successful_documents: int = Field(ge=0)
    partial_documents: int = Field(ge=0)
    failed_documents: int = Field(ge=0)
    reused_documents: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    observed_feature_count: int = Field(ge=0)
    evidence_unit_count: int = Field(ge=0)
    total_characters: int = Field(ge=0)
    total_words: int = Field(ge=0)
    exact_publication_dates: int = Field(ge=0)
    missing_publication_dates: int = Field(ge=0)
    earliest_publication: datetime | None
    latest_publication: datetime | None
    build_eligible: bool
    generation_enabled_for_evaluation: bool
    failed_analyzers: int = Field(ge=0)
    platforms: tuple[CountBreakdownResponse, ...]
    sources: tuple[CountBreakdownResponse, ...]
    languages: tuple[CountBreakdownResponse, ...]
    document_types: tuple[CountBreakdownResponse, ...]
    content_types: tuple[CountBreakdownResponse, ...]
    source_modalities: tuple[CountBreakdownResponse, ...]
    acquisition_methods: tuple[CountBreakdownResponse, ...]
    capture_media: tuple[CountBreakdownResponse, ...]
    evidence_unit_types: tuple[CountBreakdownResponse, ...]
    reposts: int = Field(ge=0)
    quote_posts: int = Field(ge=0)
    uncertain_documents: int = Field(ge=0)
    development_only_documents: int = Field(ge=0)
    issues: tuple[CorpusIssueResponse, ...]


class ReleaseAnalyticsResponse(BaseModel):
    """Immutable HVM release and structural-validation identity."""

    release_id: UUID
    version: int = Field(ge=1)
    status: str
    artifact_status: str
    authority: str
    content_hash: str
    previous_release_id: UUID | None
    registry_version: str
    registry_hash: str
    compiler_version: str
    validator_version: str
    structurally_valid: bool
    validation_issue_count: int = Field(ge=0)
    lifecycle_event_count: int = Field(ge=1)
    created_at: datetime
    published_at: datetime
    inspected_at: datetime
    summary: str


class FeatureMetricResponse(BaseModel):
    """One scalar HVM component with scope, support, and decision metadata."""

    feature_id: str
    version: str
    display_name: str
    dimension: str
    value: float
    unit: str
    decision_state: str
    confidence_coverage: float = Field(ge=0, le=1)
    support_count: int = Field(ge=0)
    platform: str | None
    scope: str


class DimensionCoverageResponse(BaseModel):
    """Coverage summary for one HVM voice dimension."""

    dimension: str
    core_feature_count: int = Field(ge=0)
    total_component_count: int = Field(ge=0)
    average_coverage: float = Field(ge=0, le=1)
    support_links: int = Field(ge=0)


class ComparisonValueResponse(BaseModel):
    """One leader's core measurement in a cross-profile comparison."""

    profile_slug: str
    profile_name: str
    value: float


class FeatureComparisonResponse(BaseModel):
    """Like-for-like core HVM measurements across published profiles."""

    feature_id: str
    display_name: str
    dimension: str
    unit: str
    values: tuple[ComparisonValueResponse, ...]


class ProfileAnalyticsResponse(BaseModel):
    """Reviewer-facing, aggregate-only inspection of one published voice profile."""

    slug: str
    name: str
    role: str
    summary: str
    corpus: CorpusAnalyticsResponse
    release: ReleaseAnalyticsResponse
    dimensions: tuple[DimensionCoverageResponse, ...]
    features: tuple[FeatureMetricResponse, ...]
    comparisons: tuple[FeatureComparisonResponse, ...]
    limitations: tuple[str, ...]
    evidence_count_explanation: str
    hvm_formula: str
    trust_statement: str


class WalkthroughResponse(BaseModel):
    slug: str
    profile_slug: str
    profile_name: str
    title: str
    platform: str
    content_type: str
    thread_post_count: int | None
    virality_influence: float
    minimum_words: int | None
    maximum_words: int | None
    idea: str
    constraints: str
    human_edit: str


class HealthResponse(BaseModel):
    status: str
    service: str
    showcase_enabled: bool
    model_enabled: bool
    model_provider: str | None = None
    mode: str
    profile_count: int
