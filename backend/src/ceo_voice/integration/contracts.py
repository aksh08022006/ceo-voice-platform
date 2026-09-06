"""Integration command, artifacts, diagnostics, timeline, and profiling contracts."""

from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import Field

from ceo_voice.context import GenerationContext
from ceo_voice.generation import GeneratedDraft
from ceo_voice.generation.contracts import RenderedPrompt
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.profiles import CuratedCorpus, ProfileBuildManifest, PublishedVoiceProfile
from ceo_voice.retrieval import RetrievalBundle
from ceo_voice.retrieval.ranking_contracts import RetrievalRankingInput
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.virality import ViralityCorpus, ViralityProfile
from ceo_voice.virality.contracts import CorpusAnalysis


class IntegrationStage(StrEnum):
    PROFILE = "voice_profile"
    VIRALITY = "virality_profile"
    AUTHORIZATION = "generation_authorization"
    CONTEXT = "generation_context"
    RETRIEVAL = "retrieval_bundle"
    PROMPT = "rendered_prompt"
    GENERATION = "generated_draft"


class IntegrationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class IntegrationInput(ContractModel):
    run_id: UUID
    profile_manifest: ProfileBuildManifest
    virality_corpus: ViralityCorpus
    request: GenerationRequest
    output_directory: Path
    started_at: UtcDatetime


class PublishedIntegrationInput(ContractModel):
    """Pinned published artifacts required to serve without rebuilding knowledge releases."""

    run_id: UUID
    profile: PublishedVoiceProfile
    profile_corpus: CuratedCorpus
    virality_profile: ViralityProfile
    virality_analysis: CorpusAnalysis
    virality_corpus: ViralityCorpus
    request: GenerationRequest
    output_directory: Path
    started_at: UtcDatetime


class TimelineEvent(ContractModel):
    stage: IntegrationStage
    started_offset_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    succeeded: bool
    detail: NonEmptyStr


class ProfilingMetrics(ContractModel):
    total_duration_ms: int = Field(ge=0)
    stage_duration_ms: dict[IntegrationStage, int]
    corpus_documents: int = Field(ge=1)
    virality_documents: int = Field(ge=1)
    evidence_items: int = Field(ge=0)
    prompt_input_tokens: int = Field(ge=0)
    provider_attempts: int = Field(ge=0)


class FailureDiagnostic(ContractModel):
    stage: IntegrationStage
    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool
    details: dict[str, str] = Field(default_factory=dict)


class IntegrationArtifacts(ContractModel):
    voice_profile: PublishedVoiceProfile | None = None
    virality_profile: ViralityProfile | None = None
    context: GenerationContext | None = None
    retrieval: RetrievalBundle | None = None
    retrieval_ranking: RetrievalRankingInput | None = Field(default=None, exclude=True)
    rendered_prompt: RenderedPrompt | None = None
    draft: GeneratedDraft | None = None


class IntegrationOutcome(ContractModel):
    run_id: UUID
    status: IntegrationStatus
    artifacts: IntegrationArtifacts
    timeline: tuple[TimelineEvent, ...]
    metrics: ProfilingMetrics
    failure: FailureDiagnostic | None
    artifact_directory: Path
    completed_at: UtcDatetime
