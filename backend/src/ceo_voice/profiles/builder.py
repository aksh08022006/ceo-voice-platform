"""End-to-end, restartable corpus-to-published-profile orchestration."""

import asyncio
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue

from ceo_voice.analysis import AnalysisEngine, AnalysisRequest, ObservationSet
from ceo_voice.core.exceptions import ApplicationError, ProfileBuildError
from ceo_voice.core.logging import get_logger
from ceo_voice.models.base import UtcDatetime
from ceo_voice.profiles.compilation import (
    DescriptivePartialPooler,
    DescriptivePlatformResidualEstimator,
    DescriptiveScalarAggregator,
    EmptyDriftEstimator,
    EmptyInteractionEstimator,
    EvidenceDerivedConfidenceEstimator,
    ScalarBaselineResidualComputer,
)
from ceo_voice.profiles.contracts import (
    BuildCheckpoint,
    CorpusObservationBatch,
    CuratedCorpus,
    CuratedDocument,
    DocumentAnalysisFailure,
    ObservationCacheKey,
    ProfileBuildManifest,
    ProfileBuildPolicy,
    ProgressEvent,
    PublishedVoiceProfile,
    ScalarBaselineSnapshot,
)
from ceo_voice.profiles.enums import BuildStage, ProgressKind
from ceo_voice.profiles.ports import NullProgressSink, ProfileWorkspace, ProgressSink
from ceo_voice.profiles.reporting import (
    build_corpus_health,
    build_inspection_report,
    build_retrieval_projection,
)
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice import (
    CompilationRequest,
    EvidenceSnapshot,
    FeatureRegistry,
    HVMRelease,
    LifecycleCommand,
    ManagedRelease,
    ProfileCompiler,
    ReleaseManager,
    ReleaseStatus,
    SemanticVersion,
    SourceModality,
    StructuralReleaseValidator,
    ValidationReport,
)

logger = get_logger(__name__)


class CorpusAnalyzer:
    """Analyze a curated corpus concurrently while reusing immutable document results."""

    def __init__(
        self,
        *,
        engine: AnalysisEngine,
        registry: FeatureRegistry,
        workspace: ProfileWorkspace,
        analyzer_signature: str,
        maximum_parallel_documents: int,
        progress: ProgressSink,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._workspace = workspace
        self._analyzer_signature = analyzer_signature
        self._maximum_parallel_documents = maximum_parallel_documents
        self._progress = progress

    async def analyze(
        self, *, build_id: UUID, corpus: CuratedCorpus, occurred_at: UtcDatetime
    ) -> CorpusObservationBatch:
        """Return successful cached/new sets and isolated document failures."""

        semaphore = asyncio.Semaphore(self._maximum_parallel_documents)
        completed = 0
        completed_lock = asyncio.Lock()

        async def process(
            item: CuratedDocument,
        ) -> tuple[ObservationSet | None, DocumentAnalysisFailure | None, bool]:
            nonlocal completed
            document = item.document
            async with semaphore:
                run_id = uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        (
                            str(document.id),
                            str(document.version),
                            document.document_fingerprint,
                            self._registry.reference.snapshot_hash,
                            self._analyzer_signature,
                        )
                    ),
                )
                key = ObservationCacheKey(
                    analysis_run_id=run_id,
                    document_id=document.id,
                    document_version=document.version,
                    document_fingerprint=document.document_fingerprint,
                    registry_snapshot_hash=self._registry.reference.snapshot_hash,
                )
                cached = await self._workspace.get_observations(key)
                reused = cached is not None
                failure: DocumentAnalysisFailure | None = None
                result = cached
                if result is None:
                    if item.source_modality is not SourceModality.AUTHORED_WRITTEN:
                        failure = DocumentAnalysisFailure(
                            document_id=document.id,
                            document_version=document.version,
                            code="unsupported_source_modality",
                            message=(
                                "Tier 1 analyzers currently admit authored written evidence only."
                            ),
                        )
                    else:
                        try:
                            result = await self._engine.analyze(
                                AnalysisRequest(
                                    run_id=run_id,
                                    document=document,
                                    voice_identity=corpus.identity,
                                    source_modality=item.source_modality,
                                    event_time=document.publication_date or document.processed_at,
                                    created_at=document.processed_at,
                                )
                            )
                            if not result.observations:
                                failure = DocumentAnalysisFailure(
                                    document_id=document.id,
                                    document_version=document.version,
                                    code="analysis_produced_no_observations",
                                    message="Document analysis produced no usable observations.",
                                )
                                result = None
                            else:
                                await self._workspace.save_observations(key, result)
                        except Exception as exc:  # document isolation boundary
                            failure = DocumentAnalysisFailure(
                                document_id=document.id,
                                document_version=document.version,
                                code=(
                                    exc.code
                                    if isinstance(exc, ApplicationError)
                                    else "document_analysis_error"
                                ),
                                message="Document analysis failed at an isolated boundary.",
                            )
                async with completed_lock:
                    completed += 1
                    current = completed
                kind = (
                    ProgressKind.DOCUMENT_FAILED
                    if failure is not None
                    else ProgressKind.DOCUMENT_REUSED if reused else ProgressKind.DOCUMENT_ANALYZED
                )
                self._report(
                    ProgressEvent(
                        build_id=build_id,
                        kind=kind,
                        stage=BuildStage.ANALYZING,
                        completed=current,
                        total=len(corpus.documents),
                        occurred_at=occurred_at,
                        document_id=document.id,
                        message=(
                            failure.message
                            if failure is not None
                            else (
                                "Reused immutable observations." if reused else "Analyzed document."
                            )
                        ),
                    )
                )
                return result, failure, reused

        raw_results = await asyncio.gather(
            *(
                process(item)
                for item in sorted(corpus.documents, key=lambda item: item.document.id.int)
            )
        )
        observation_sets = tuple(
            sorted(
                (item[0] for item in raw_results if item[0] is not None),
                key=lambda item: item.document_id,
            )
        )
        failures = tuple(item[1] for item in raw_results if item[1] is not None)
        return CorpusObservationBatch(
            observation_sets=observation_sets,
            failures=failures,
            analyzed_documents=sum(item[0] is not None and not item[2] for item in raw_results),
            reused_documents=sum(item[0] is not None and item[2] for item in raw_results),
        )

    def _report(self, event: ProgressEvent) -> None:
        try:
            self._progress.report(event)
        except Exception as exc:
            logger.warning(
                "progress sink failed",
                extra={"event_kind": event.kind, "error_type": type(exc).__name__},
            )


class VoiceProfileBuilder:
    """Connect analysis, compilation, validation, lifecycle, reporting, and publication."""

    def __init__(
        self,
        *,
        analysis_engine: AnalysisEngine,
        registry: FeatureRegistry,
        baselines: ScalarBaselineSnapshot,
        workspace: ProfileWorkspace,
        analyzer_signature: str,
        policy: ProfileBuildPolicy | None = None,
        progress: ProgressSink | None = None,
    ) -> None:
        self._registry = registry
        self._baselines = baselines
        self._analyzer_signature = analyzer_signature
        self._workspace = workspace
        self._policy = policy or ProfileBuildPolicy()
        self._progress = progress or NullProgressSink()
        self._corpus_analyzer = CorpusAnalyzer(
            engine=analysis_engine,
            registry=registry,
            workspace=workspace,
            analyzer_signature=analyzer_signature,
            maximum_parallel_documents=self._policy.maximum_parallel_documents,
            progress=self._progress,
        )

    async def build(self, manifest: ProfileBuildManifest) -> PublishedVoiceProfile:
        """Build or resume one exact corpus and optionally activate its immutable release."""

        corpus_hash = self._corpus_hash(manifest.corpus)
        existing_profile = await self._workspace.get_published(
            manifest.corpus.identity.id, corpus_hash
        )
        if existing_profile is not None and (
            not manifest.publish or existing_profile.managed_release.status is ReleaseStatus.ACTIVE
        ):
            return existing_profile
        checkpoint = await self._checkpoint(manifest, corpus_hash)
        self._report(
            checkpoint,
            ProgressKind.BUILD_STARTED,
            BuildStage.ANALYZING,
            0,
            len(manifest.corpus.documents),
            "Profile build started or resumed.",
        )
        try:
            checkpoint = checkpoint.model_copy(
                update={
                    "stage": BuildStage.ANALYZING,
                    "updated_at": checkpoint.requested_at,
                    "last_error_code": None,
                }
            )
            await self._workspace.save_checkpoint(checkpoint)
            batch = await self._corpus_analyzer.analyze(
                build_id=checkpoint.build_id,
                corpus=manifest.corpus,
                occurred_at=checkpoint.requested_at,
            )
            health = build_corpus_health(
                corpus_hash=corpus_hash,
                corpus=manifest.corpus,
                batch=batch,
                policy=self._policy,
            )
            if not health.build_eligible:
                raise ProfileBuildError(
                    "corpus does not satisfy profile build gates",
                    details={"issue_codes": tuple(item.code for item in health.issues)},
                )
            observations = tuple(
                sorted(
                    (
                        item
                        for observation_set in batch.observation_sets
                        for item in observation_set.observations
                    ),
                    key=lambda item: item.id.int,
                )
            )
            evidence_by_id = {
                item.id: item
                for observation_set in batch.observation_sets
                for item in observation_set.evidence_units
            }
            evidence_units = tuple(sorted(evidence_by_id.values(), key=lambda item: item.id.int))
            checkpoint = checkpoint.model_copy(
                update={"stage": BuildStage.COMPILING, "updated_at": checkpoint.requested_at}
            )
            await self._workspace.save_checkpoint(checkpoint)
            self._report(
                checkpoint,
                ProgressKind.COMPILATION_STARTED,
                BuildStage.COMPILING,
                len(batch.observation_sets),
                len(manifest.corpus.documents),
                "HVM compilation started.",
            )
            evidence_snapshot = EvidenceSnapshot.build(
                snapshot_id=checkpoint.evidence_snapshot_id,
                tenant_id=manifest.corpus.identity.tenant_id,
                voice_identity_id=manifest.corpus.identity.id,
                evidence_units=evidence_units,
                created_at=checkpoint.requested_at,
            )
            previous = await self._previous_release(manifest.corpus, checkpoint.release_id)
            compiler = self._compiler(checkpoint.requested_at)
            compiled = compiler.compile(
                CompilationRequest(
                    build_id=checkpoint.build_id,
                    release_id=checkpoint.release_id,
                    release_version=checkpoint.release_version,
                    validation_report_id=checkpoint.validation_report_id,
                    identity=manifest.corpus.identity,
                    lineage=manifest.corpus.lineage,
                    evidence_snapshot=evidence_snapshot,
                    evidence_units=evidence_units,
                    observations=observations,
                    previous_release=previous,
                    created_at=checkpoint.requested_at,
                    validated_at=checkpoint.requested_at,
                )
            )
            checkpoint = checkpoint.model_copy(
                update={"stage": BuildStage.PUBLISHING, "updated_at": checkpoint.requested_at}
            )
            await self._workspace.save_checkpoint(checkpoint)
            self._report(
                checkpoint,
                ProgressKind.PUBLICATION_STARTED,
                BuildStage.PUBLISHING,
                0,
                1,
                "Release publication started.",
            )
            managed = await self._publish(
                checkpoint=checkpoint,
                actor_id=manifest.actor_id,
                release=compiled.release,
                report=compiled.validation_report,
                publish=manifest.publish,
            )
            projection = build_retrieval_projection(
                projection_id=checkpoint.projection_id,
                release=compiled.release,
                materialized_at=checkpoint.requested_at,
            )
            inspection = build_inspection_report(
                managed_release=managed,
                registry=self._registry,
                health=health,
                generated_at=checkpoint.requested_at,
            )
            profile = PublishedVoiceProfile(
                build_id=checkpoint.build_id,
                corpus_hash=corpus_hash,
                managed_release=managed,
                validation_report=compiled.validation_report,
                observations=observations,
                evidence_units=evidence_units,
                corpus_health=health,
                inspection=inspection,
                retrieval_projection=projection,
                published_at=checkpoint.requested_at,
            )
            await self._workspace.save_published(profile)
            checkpoint = checkpoint.model_copy(
                update={"stage": BuildStage.COMPLETED, "updated_at": checkpoint.requested_at}
            )
            await self._workspace.save_checkpoint(checkpoint)
            self._report(
                checkpoint,
                ProgressKind.BUILD_COMPLETED,
                BuildStage.COMPLETED,
                1,
                1,
                "Profile build completed.",
            )
            return profile
        except Exception as exc:
            code = exc.code if isinstance(exc, ApplicationError) else "profile_build_error"
            failed = checkpoint.model_copy(
                update={
                    "stage": BuildStage.FAILED,
                    "updated_at": checkpoint.requested_at,
                    "last_error_code": code,
                }
            )
            await self._workspace.save_checkpoint(failed)
            self._report(
                failed,
                ProgressKind.BUILD_FAILED,
                BuildStage.FAILED,
                0,
                1,
                "Profile build failed; checkpoint retained for recovery.",
            )
            if isinstance(exc, ApplicationError):
                raise
            raise ProfileBuildError("profile build failed unexpectedly") from exc

    async def _checkpoint(
        self, manifest: ProfileBuildManifest, corpus_hash: str
    ) -> BuildCheckpoint:
        existing = await self._workspace.get_checkpoint(manifest.corpus.identity.id, corpus_hash)
        if existing is not None:
            return existing
        lineage = await self._workspace.list_lineage(
            manifest.corpus.identity.tenant_id, manifest.corpus.lineage.id
        )
        release_version = max((item.release.version for item in lineage), default=0) + 1
        base = f"{manifest.corpus.identity.id}:{corpus_hash}:{release_version}"
        checkpoint = BuildCheckpoint(
            build_id=uuid5(NAMESPACE_URL, f"{base}:build"),
            corpus_hash=corpus_hash,
            voice_identity_id=manifest.corpus.identity.id,
            lineage_id=manifest.corpus.lineage.id,
            release_id=uuid5(NAMESPACE_URL, f"{base}:release"),
            release_version=release_version,
            validation_report_id=uuid5(NAMESPACE_URL, f"{base}:validation"),
            evidence_snapshot_id=uuid5(NAMESPACE_URL, f"{base}:evidence"),
            projection_id=uuid5(NAMESPACE_URL, f"{base}:projection"),
            stage=BuildStage.ANALYZING,
            requested_at=manifest.requested_at,
            updated_at=manifest.requested_at,
        )
        await self._workspace.save_checkpoint(checkpoint)
        return checkpoint

    async def _previous_release(
        self, corpus: CuratedCorpus, current_release_id: UUID
    ) -> HVMRelease | None:
        lineage = await self._workspace.list_lineage(corpus.identity.tenant_id, corpus.lineage.id)
        previous = tuple(item.release for item in lineage if item.release.id != current_release_id)
        return max(previous, key=lambda item: item.version) if previous else None

    def _compiler(self, created_at: UtcDatetime) -> ProfileCompiler:
        validator = StructuralReleaseValidator(
            registry=self._registry, version=SemanticVersion.parse("1.0.0")
        )
        return ProfileCompiler(
            registry=self._registry,
            aggregator=DescriptiveScalarAggregator(registry=self._registry, created_at=created_at),
            partial_pooler=DescriptivePartialPooler(),
            residual_computer=ScalarBaselineResidualComputer(
                baselines=self._baselines, created_at=created_at
            ),
            conditional_residual_estimator=DescriptivePlatformResidualEstimator(
                created_at=created_at
            ),
            interaction_estimator=EmptyInteractionEstimator(),
            drift_estimator=EmptyDriftEstimator(),
            confidence_estimator=EvidenceDerivedConfidenceEstimator(),
            validator=validator,
            compiler_version=SemanticVersion.parse("1.0.0"),
        )

    async def _publish(
        self,
        *,
        checkpoint: BuildCheckpoint,
        actor_id: UUID,
        release: HVMRelease,
        report: ValidationReport,
        publish: bool,
    ) -> ManagedRelease:
        manager = ReleaseManager(catalog=self._workspace)
        record = await self._workspace.get(release.tenant_id, release.id)
        if record is None:
            record = await manager.create(
                release,
                command=self._command(checkpoint, actor_id, "created"),
            )
        elif record.release != release:
            raise ProfileBuildError("checkpoint release conflicts with compiled content")
        while True:
            if record.status is ReleaseStatus.BUILDING:
                record = await manager.begin_validation(
                    release.tenant_id,
                    release.id,
                    command=self._command(checkpoint, actor_id, "validation_started"),
                )
            elif record.status is ReleaseStatus.VALIDATING:
                record = await manager.complete_validation(
                    release.tenant_id,
                    release.id,
                    report,
                    command=self._command(checkpoint, actor_id, "validation_completed"),
                )
            elif record.status is ReleaseStatus.NEEDS_REVIEW:
                if not publish:
                    return record
                record = await manager.approve(
                    release.tenant_id,
                    release.id,
                    command=self._command(checkpoint, actor_id, "approved"),
                )
            elif record.status is ReleaseStatus.APPROVED:
                if not publish:
                    return record
                lineage = await self._workspace.list_lineage(release.tenant_id, release.lineage_id)
                active = next(
                    (
                        item
                        for item in lineage
                        if item.status is ReleaseStatus.ACTIVE and item.release.id != release.id
                    ),
                    None,
                )
                record = await manager.activate(
                    release.tenant_id,
                    release.id,
                    activation=self._command(checkpoint, actor_id, "activated"),
                    supersession=(
                        LifecycleCommand(
                            event_id=uuid5(
                                NAMESPACE_URL,
                                f"{checkpoint.release_id}:{active.release.id}:superseded",
                            ),
                            actor_id=actor_id,
                            occurred_at=checkpoint.requested_at,
                        )
                        if active is not None
                        else None
                    ),
                )
            elif record.status in {ReleaseStatus.ACTIVE, ReleaseStatus.NEEDS_REVIEW}:
                return record
            else:
                raise ProfileBuildError(
                    "release cannot resume publication from its current status",
                    details={"status": record.status.value},
                )

    @staticmethod
    def _command(checkpoint: BuildCheckpoint, actor_id: UUID, event_name: str) -> LifecycleCommand:
        return LifecycleCommand(
            event_id=uuid5(NAMESPACE_URL, f"{checkpoint.release_id}:{event_name}"),
            actor_id=actor_id,
            occurred_at=checkpoint.requested_at,
        )

    def _corpus_hash(self, corpus: CuratedCorpus) -> str:
        payload = cast(
            JsonValue,
            {
                "profile_builder_schema": "1.0.0",
                "identity_id": str(corpus.identity.id),
                "lineage_id": str(corpus.lineage.id),
                "feature_registry_hash": self._registry.reference.snapshot_hash,
                "analyzer_signature": self._analyzer_signature,
                "baseline_snapshot": self._baselines.model_dump(mode="json"),
                "documents": [
                    {
                        "id": str(item.document.id),
                        "version": item.document.version,
                        "fingerprint": item.document.document_fingerprint,
                        "modality": item.source_modality.value,
                    }
                    for item in sorted(corpus.documents, key=lambda item: item.document.id.int)
                ],
            },
        )
        return sha256_text(dumps_json(payload))

    def _report(
        self,
        checkpoint: BuildCheckpoint,
        kind: ProgressKind,
        stage: BuildStage,
        completed: int,
        total: int,
        message: str,
    ) -> None:
        try:
            self._progress.report(
                ProgressEvent(
                    build_id=checkpoint.build_id,
                    kind=kind,
                    stage=stage,
                    completed=completed,
                    total=total,
                    occurred_at=checkpoint.requested_at,
                    message=message,
                )
            )
        except Exception as exc:
            logger.warning(
                "progress sink failed",
                extra={"event_kind": kind, "error_type": type(exc).__name__},
            )
