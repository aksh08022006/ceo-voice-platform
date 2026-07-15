"""Stable browser-facing request and response contracts."""

from uuid import UUID

from pydantic import BaseModel, Field

from ceo_voice.models.enums import Platform


class GenerateWorkflowRequest(BaseModel):
    """Inputs supplied by the Generate workspace."""

    profile_slug: str = Field(min_length=1)
    platform: Platform
    content_type: str = Field(pattern=r"^(post|thread|announcement)$")
    idea: str = Field(min_length=20, max_length=1_200)
    constraints: str = Field(default="", max_length=600)


class ReVoiceWorkflowRequest(BaseModel):
    """Human-edited draft submitted to the Re-Voice engine."""

    content: str = Field(min_length=1, max_length=20_000)


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
    profile_slug: str
    profile_name: str
    platform: str
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


class WalkthroughResponse(BaseModel):
    slug: str
    profile_slug: str
    profile_name: str
    title: str
    platform: str
    content_type: str
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
