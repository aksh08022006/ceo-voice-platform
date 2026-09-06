"""Production serving orchestration over already-published immutable knowledge."""

from datetime import timedelta
from time import monotonic_ns

from ceo_voice.context import CompilationInput, ContextCompiler
from ceo_voice.core.exceptions import ApplicationError, IntegrationError
from ceo_voice.generation import GenerationEngine, GenerationInput, PromptBuilder, PromptRenderer
from ceo_voice.integration.artifacts import ArtifactWriter
from ceo_voice.integration.contracts import (
    FailureDiagnostic,
    IntegrationArtifacts,
    IntegrationOutcome,
    IntegrationStage,
    IntegrationStatus,
    ProfilingMetrics,
    PublishedIntegrationInput,
    TimelineEvent,
)
from ceo_voice.integration.evidence import materialize_evidence
from ceo_voice.integration.ports import RetrievalRankingPreparer
from ceo_voice.retrieval import (
    InMemoryEvidenceMaterialReader,
    RetrievalInput,
    RetrievalIntelligenceEngine,
)
from ceo_voice.virality.releases import build_analysis_snapshot
from ceo_voice.voice import FeatureRegistry


class PublishedIntegrationRunner:
    """Serve one request from pinned HVM/VKR releases without invoking either builder."""

    def __init__(
        self,
        *,
        feature_registry: FeatureRegistry,
        context_compiler: ContextCompiler,
        prompt_builder: PromptBuilder,
        prompt_renderer: PromptRenderer,
        generation_engine: GenerationEngine,
        artifacts: ArtifactWriter | None = None,
        retrieval_ranking: RetrievalRankingPreparer | None = None,
    ) -> None:
        self._registry = feature_registry
        self._context_compiler = context_compiler
        self._prompt_builder = prompt_builder
        self._prompt_renderer = prompt_renderer
        self._generation_engine = generation_engine
        self._writer = artifacts or ArtifactWriter()
        self._retrieval_ranking = retrieval_ranking

    async def run(self, command: PublishedIntegrationInput) -> IntegrationOutcome:
        """Authorize, compile, retrieve, prompt, and generate from immutable inputs."""

        started = monotonic_ns()
        stage_start = started
        current = IntegrationStage.AUTHORIZATION
        timeline: list[TimelineEvent] = []
        artifacts = IntegrationArtifacts(
            voice_profile=command.profile,
            virality_profile=command.virality_profile,
        )
        failure: FailureDiagnostic | None = None
        status = IntegrationStatus.SUCCEEDED
        try:
            self._authorize(command)
            self._record(timeline, current, started, stage_start, "published artifacts authorized")

            current = IntegrationStage.CONTEXT
            stage_start = monotonic_ns()
            context = self._context_compiler.compile(
                CompilationInput(
                    request=command.request,
                    target_identity=command.profile_corpus.identity,
                    voice_release=command.profile.managed_release,
                    feature_registry=self._registry,
                    virality_profile=command.virality_profile,
                    compiled_at=command.started_at,
                )
            )
            artifacts = artifacts.model_copy(update={"context": context})
            self._record(timeline, current, started, stage_start, "compiled generation context")

            current = IntegrationStage.RETRIEVAL
            stage_start = monotonic_ns()
            materials = materialize_evidence(
                command.profile,
                command.profile_corpus,
                command.virality_analysis,
                command.virality_corpus,
            )
            retrieval_input = RetrievalInput(
                request=command.request,
                context=context,
                voice_profile=command.profile,
                virality_profile=command.virality_profile,
                retrieved_at=command.started_at,
            )
            engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials))
            if self._retrieval_ranking is not None:
                eligible = await engine.candidate_materials(retrieval_input)
                ranking = await self._retrieval_ranking.prepare(retrieval_input, eligible)
                retrieval_input = retrieval_input.model_copy(update={"ranking": ranking})
                artifacts = artifacts.model_copy(update={"retrieval_ranking": ranking})
            retrieval = await engine.retrieve(retrieval_input)
            artifacts = artifacts.model_copy(update={"retrieval": retrieval})
            self._record(timeline, current, started, stage_start, "assembled retrieval bundle")

            generation_input = GenerationInput(
                request=command.request,
                context=context,
                retrieval=retrieval,
                generated_at=command.started_at,
            )
            current = IntegrationStage.PROMPT
            stage_start = monotonic_ns()
            rendered = self._prompt_renderer.render(self._prompt_builder.build(generation_input))
            artifacts = artifacts.model_copy(update={"rendered_prompt": rendered})
            self._record(timeline, current, started, stage_start, "rendered governed prompt")

            current = IntegrationStage.GENERATION
            stage_start = monotonic_ns()
            draft = await self._generation_engine.generate(generation_input)
            artifacts = artifacts.model_copy(update={"draft": draft})
            self._record(timeline, current, started, stage_start, "generated validated draft")
        except Exception as error:
            status = (
                IntegrationStatus.BLOCKED
                if isinstance(error, IntegrationError)
                else IntegrationStatus.FAILED
            )
            if not timeline or timeline[-1].stage is not current:
                self._record(timeline, current, started, stage_start, str(error), succeeded=False)
            failure = self._diagnostic(current, error)

        total_ms = self._milliseconds(monotonic_ns() - started)
        final_draft = artifacts.draft
        outcome = IntegrationOutcome(
            run_id=command.run_id,
            status=status,
            artifacts=artifacts,
            timeline=tuple(timeline),
            metrics=ProfilingMetrics(
                total_duration_ms=total_ms,
                stage_duration_ms={item.stage: item.duration_ms for item in timeline},
                corpus_documents=len(command.profile_corpus.documents),
                virality_documents=len(command.virality_corpus.items),
                evidence_items=len(artifacts.retrieval.evidence) if artifacts.retrieval else 0,
                prompt_input_tokens=(
                    artifacts.rendered_prompt.estimated_input_tokens
                    if artifacts.rendered_prompt
                    else 0
                ),
                provider_attempts=len(final_draft.report.attempts) if final_draft else 0,
            ),
            failure=failure,
            artifact_directory=command.output_directory / str(command.run_id),
            completed_at=command.started_at + timedelta(milliseconds=total_ms),
        )
        self._writer.write_outcome(outcome)
        return outcome

    @staticmethod
    def _authorize(command: PublishedIntegrationInput) -> None:
        profile = command.profile
        if not profile.corpus_health.generation_ready:
            raise IntegrationError(
                "published voice profile is not authorized for generation",
                details={
                    "reason": "profile_not_generation_ready",
                    "release_id": str(profile.managed_release.release.id),
                },
            )
        snapshot = command.virality_profile.publication.release.analysis_snapshot
        if snapshot.corpus_id != command.virality_corpus.id:
            raise IntegrationError(
                "published VKR does not reference the supplied corpus",
                details={"reason": "virality_corpus_mismatch"},
            )
        rebuilt = build_analysis_snapshot(
            snapshot_id=snapshot.id,
            analysis=command.virality_analysis,
            corpus_id=command.virality_corpus.id,
        )
        if rebuilt != snapshot:
            raise IntegrationError(
                "VKR analysis does not match the published snapshot",
                details={"reason": "virality_analysis_mismatch"},
            )

    @classmethod
    def _record(
        cls,
        timeline: list[TimelineEvent],
        stage: IntegrationStage,
        run_start: int,
        stage_start: int,
        detail: str,
        *,
        succeeded: bool = True,
    ) -> None:
        timeline.append(
            TimelineEvent(
                stage=stage,
                started_offset_ms=cls._milliseconds(stage_start - run_start),
                duration_ms=cls._milliseconds(monotonic_ns() - stage_start),
                succeeded=succeeded,
                detail=detail or "stage failed",
            )
        )

    @staticmethod
    def _diagnostic(stage: IntegrationStage, error: Exception) -> FailureDiagnostic:
        if isinstance(error, ApplicationError):
            return FailureDiagnostic(
                stage=stage,
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details={str(key): str(value) for key, value in error.details.items()},
            )
        return FailureDiagnostic(
            stage=stage,
            code="unexpected_integration_error",
            message=str(error) or type(error).__name__,
            retryable=False,
            details={"error_type": type(error).__name__},
        )

    @staticmethod
    def _milliseconds(nanoseconds: int) -> int:
        return max(0, nanoseconds // 1_000_000)
