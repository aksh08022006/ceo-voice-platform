"""Dependency-aware asynchronous execution engine for pure feature analyzers."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import cast

from pydantic import JsonValue

from ceo_voice.analysis.builder import ObservationBuilder
from ceo_voice.analysis.contracts import (
    AnalysisRequest,
    AnalyzerContext,
    AnalyzerExecutionRecord,
    MeasurementCandidate,
    ObservationSet,
)
from ceo_voice.analysis.document import DeterministicDocumentAnalyzer
from ceo_voice.analysis.enums import AnalysisRunStatus, AnalyzerRunStatus
from ceo_voice.analysis.ports import (
    Analyzer,
    AnalyzerResultCache,
    ConfidenceComposer,
    ExecutionMetricsSink,
)
from ceo_voice.analysis.registry import AnalyzerRegistry
from ceo_voice.core.exceptions import ApplicationError, ObservationBuildError
from ceo_voice.core.logging import get_logger
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.evidence import EvidenceUnit
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.ports import FeatureRegistryReader
from ceo_voice.voice.primitives import FeatureReference

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ExecutionResult:
    analyzer: Analyzer
    candidates: tuple[MeasurementCandidate, ...]
    status: AnalyzerRunStatus
    error_code: str | None = None


class AnalysisEngine:
    """Compile a clean document into canonical evidence-backed observations."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        feature_registry: FeatureRegistryReader,
        document_analyzer: DeterministicDocumentAnalyzer,
        confidence_composer: ConfidenceComposer,
        cache: AnalyzerResultCache | None = None,
        metrics_sink: ExecutionMetricsSink | None = None,
    ) -> None:
        self._analyzer_registry = analyzer_registry
        self._feature_registry = feature_registry
        self._document_analyzer = document_analyzer
        self._builder = ObservationBuilder(
            feature_registry=feature_registry,
            confidence_composer=confidence_composer,
        )
        self._cache = cache
        self._metrics_sink = metrics_sink

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        features: tuple[FeatureReference, ...] | None = None,
    ) -> ObservationSet:
        """Execute compatible analyzers with dependency ordering and failure isolation."""

        analyzed_document = self._document_analyzer.analyze(request.document)
        levels = self._analyzer_registry.plan(document=request.document, features=features)
        results: dict[str, tuple[MeasurementCandidate, ...]] = {}
        statuses: dict[str, AnalyzerRunStatus] = {}
        observations: list[Observation] = []
        evidence: dict[object, EvidenceUnit] = {}
        trace: list[AnalyzerExecutionRecord] = []

        for level_index, level in enumerate(levels):
            runnable: list[Analyzer] = []
            for analyzer in level:
                dependencies = analyzer.specification.dependencies
                if any(
                    statuses.get(item.analyzer_id)
                    not in {
                        AnalyzerRunStatus.SUCCEEDED,
                        AnalyzerRunStatus.CACHE_HIT,
                    }
                    for item in dependencies
                ):
                    statuses[analyzer.specification.analyzer_id] = AnalyzerRunStatus.SKIPPED
                    trace.append(
                        self._record(
                            analyzer,
                            level_index,
                            AnalyzerRunStatus.SKIPPED,
                            0,
                            "dependency_failed",
                        )
                    )
                else:
                    runnable.append(analyzer)

            executions = await asyncio.gather(
                *(
                    self._execute(
                        analyzer,
                        AnalyzerContext(
                            request=request,
                            analyzed_document=analyzed_document,
                            dependency_results={
                                dependency.analyzer_id: results[dependency.analyzer_id]
                                for dependency in analyzer.specification.dependencies
                            },
                        ),
                    )
                    for analyzer in runnable
                )
            )
            for execution in executions:
                analyzer = execution.analyzer
                analyzer_id = analyzer.specification.analyzer_id
                status = execution.status
                error_code = execution.error_code
                built_observations: list[Observation] = []
                built_evidence: dict[object, EvidenceUnit] = {}
                if status in {AnalyzerRunStatus.SUCCEEDED, AnalyzerRunStatus.CACHE_HIT}:
                    try:
                        for ordinal, candidate in enumerate(execution.candidates):
                            observation, units = self._builder.build(
                                request=request,
                                analyzed_document=analyzed_document,
                                analyzer=analyzer.specification,
                                candidate=candidate,
                                candidate_ordinal=ordinal,
                            )
                            built_observations.append(observation)
                            for unit in units:
                                existing = evidence.get(unit.id) or built_evidence.get(unit.id)
                                if existing is not None and existing != unit:
                                    raise ObservationBuildError(
                                        "evidence identifier resolved to conflicting units"
                                    )
                                built_evidence[unit.id] = unit
                    except (ApplicationError, ValueError) as exc:
                        logger.warning(
                            "analyzer output rejected",
                            extra={"analyzer_id": analyzer_id, "error_type": type(exc).__name__},
                        )
                        status = AnalyzerRunStatus.FAILED
                        error_code = (
                            exc.code if isinstance(exc, ApplicationError) else "invalid_output"
                        )
                        built_observations.clear()
                        built_evidence.clear()

                statuses[analyzer_id] = status
                if status in {AnalyzerRunStatus.SUCCEEDED, AnalyzerRunStatus.CACHE_HIT}:
                    results[analyzer_id] = execution.candidates
                    observations.extend(built_observations)
                    evidence.update(built_evidence)
                trace.append(
                    self._record(
                        analyzer,
                        level_index,
                        status,
                        len(execution.candidates) if status is not AnalyzerRunStatus.FAILED else 0,
                        error_code,
                    )
                )

        failure_present = any(
            item.status in {AnalyzerRunStatus.FAILED, AnalyzerRunStatus.SKIPPED} for item in trace
        )
        if observations and failure_present:
            run_status = AnalysisRunStatus.PARTIAL
        elif observations:
            run_status = AnalysisRunStatus.SUCCEEDED
        else:
            run_status = AnalysisRunStatus.FAILED
        return ObservationSet(
            run_id=request.run_id,
            tenant_id=request.document.tenant_id,
            voice_identity_id=request.voice_identity.id,
            document_id=request.document.id,
            document_version=request.document.version,
            registry=self._feature_registry.reference,
            status=run_status,
            observations=tuple(sorted(observations, key=lambda item: item.id.int)),
            evidence_units=tuple(sorted(evidence.values(), key=lambda item: item.id.int)),
            execution_trace=tuple(trace),
            created_at=request.created_at,
        )

    async def _execute(self, analyzer: Analyzer, context: AnalyzerContext) -> _ExecutionResult:
        specification = analyzer.specification
        cache_key = self._cache_key(
            specification.analyzer_id, specification.configuration_hash, context
        )
        started = perf_counter()
        succeeded = False
        try:
            if self._cache is not None:
                cached = await self._cache.get(cache_key)
                if cached is not None:
                    succeeded = True
                    return _ExecutionResult(analyzer, cached, AnalyzerRunStatus.CACHE_HIT)
            candidates = await analyzer.analyze(context)
            if self._cache is not None:
                await self._cache.put(cache_key, candidates)
            succeeded = True
            return _ExecutionResult(analyzer, candidates, AnalyzerRunStatus.SUCCEEDED)
        except Exception as exc:  # analyzer isolation boundary
            logger.warning(
                "analyzer execution failed",
                extra={
                    "analyzer_id": specification.analyzer_id,
                    "error_type": type(exc).__name__,
                },
            )
            code = exc.code if isinstance(exc, ApplicationError) else "analyzer_execution_error"
            return _ExecutionResult(analyzer, (), AnalyzerRunStatus.FAILED, code)
        finally:
            if self._metrics_sink is not None:
                try:
                    self._metrics_sink.record(
                        analyzer_id=specification.analyzer_id,
                        duration_seconds=perf_counter() - started,
                        succeeded=succeeded,
                    )
                except Exception as exc:  # telemetry must not control domain correctness
                    logger.warning(
                        "analyzer metrics emission failed",
                        extra={
                            "analyzer_id": specification.analyzer_id,
                            "error_type": type(exc).__name__,
                        },
                    )

    def _cache_key(
        self, analyzer_id: str, configuration_hash: str, context: AnalyzerContext
    ) -> str:
        """Create a stable key from every behavior-affecting immutable input."""

        dependency_payload = cast(
            JsonValue,
            {
                key: [candidate.model_dump(mode="json") for candidate in value]
                for key, value in sorted(context.dependency_results.items())
            },
        )
        dependency_fingerprint = sha256_text(dumps_json(dependency_payload))
        return sha256_text(
            ":".join(
                (
                    analyzer_id,
                    configuration_hash,
                    context.request.document.document_fingerprint,
                    str(context.request.document.version),
                    self._feature_registry.reference.snapshot_hash,
                    str(context.analyzed_document.segmentation_version),
                    dependency_fingerprint,
                )
            )
        )

    @staticmethod
    def _record(
        analyzer: Analyzer,
        level: int,
        status: AnalyzerRunStatus,
        candidate_count: int,
        error_code: str | None,
    ) -> AnalyzerExecutionRecord:
        return AnalyzerExecutionRecord(
            analyzer_id=analyzer.specification.analyzer_id,
            analyzer_version=analyzer.specification.version,
            level=level,
            status=status,
            candidate_count=candidate_count,
            error_code=error_code,
        )
