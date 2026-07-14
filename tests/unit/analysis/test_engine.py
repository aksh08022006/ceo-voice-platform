"""Integration tests for execution, recovery, caching, tracing, and determinism."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from ceo_voice.analysis import (
    AnalysisEngine,
    AnalysisRequest,
    AnalysisRunStatus,
    AnalyzerContext,
    AnalyzerDependency,
    AnalyzerRegistry,
    AnalyzerRunStatus,
    AnalyzerSpecification,
    DeterministicDocumentAnalyzer,
    MeasurementCandidate,
)
from ceo_voice.analysis.ports import Analyzer
from ceo_voice.voice import AggregationRequest, ScalarValue, SourceModality
from tests.unit.analysis.factories import (
    NOW,
    RUN_ID,
    analyzers,
    clean_document,
    confidence_composer,
    feature_definition,
    identity,
    registry,
    semver,
)
from tests.unit.analysis.test_registry_contracts import specification

type BehaviorResult = (
    tuple[MeasurementCandidate, ...] | Awaitable[tuple[MeasurementCandidate, ...]] | Exception
)


def request() -> AnalysisRequest:
    """Return the standard analysis request."""

    return AnalysisRequest(
        run_id=RUN_ID,
        document=clean_document(metadata={"thread_length": 3}),
        voice_identity=identity(),
        source_modality=SourceModality.AUTHORED_WRITTEN,
        event_time=NOW,
        created_at=NOW,
    )


def engine(
    registered: tuple[Analyzer, ...] | None = None,
    *,
    feature_ids: tuple[str, ...] | None = None,
    cache: object | None = None,
    metrics: object | None = None,
) -> AnalysisEngine:
    """Construct an engine with explicit test dependencies."""

    selected = registered or analyzers()
    selected_feature_ids = feature_ids or tuple(
        feature.feature_id
        for analyzer in selected
        for feature in analyzer.specification.supported_features
    )
    return AnalysisEngine(
        analyzer_registry=AnalyzerRegistry(selected),
        feature_registry=registry(feature_ids=selected_feature_ids),
        document_analyzer=DeterministicDocumentAnalyzer(segmentation_version=semver()),
        confidence_composer=confidence_composer(),
        cache=cache,  # type: ignore[arg-type]
        metrics_sink=metrics,  # type: ignore[arg-type]
    )


class ConfigurableAnalyzer:
    """Pure analyzer stub with injectable async behavior."""

    def __init__(
        self,
        analyzer_id: str,
        feature_id: str,
        behavior: Callable[[AnalyzerContext], BehaviorResult],
        *,
        dependencies: tuple[AnalyzerDependency, ...] = (),
    ) -> None:
        self._specification = specification(
            analyzer_id,
            feature_id,
            dependencies=dependencies,
        )
        self._behavior = behavior

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        result = self._behavior(context)
        if isinstance(result, Awaitable):
            return await result
        if isinstance(result, Exception):
            raise result
        return result


def one_candidate(context: AnalyzerContext, analyzer: Analyzer) -> tuple[MeasurementCandidate, ...]:
    """Return one document-scoped scalar candidate for ``analyzer``."""

    return (
        MeasurementCandidate(
            feature=analyzer.specification.supported_features[0],
            value=ScalarValue(value=1, unit="count"),
            evidence_span_ids=(context.analyzed_document.document_span.id,),
            opportunity_count=1,
        ),
    )


def test_end_to_end_tier1_output_is_hvm_consumable_and_repeatable() -> None:
    first = asyncio.run(engine().analyze(request()))
    second = asyncio.run(engine().analyze(request()))

    assert first == second
    assert first.status is AnalysisRunStatus.SUCCEEDED
    assert len(first.observations) == 38
    assert len(first.evidence_units) >= 3
    assert all(observation.evidence for observation in first.observations)
    assert all(
        observation.producer.producer_id.startswith("tier1.") for observation in first.observations
    )
    assert all(
        observation.context.platform == request().document.platform
        for observation in first.observations
    )
    snapshot = first.to_evidence_snapshot(snapshot_id=semver_uuid())
    assert len(snapshot.members) == len(first.evidence_units)
    compiler_input = AggregationRequest(
        build_id=RUN_ID,
        registry=first.registry,
        observations=first.observations,
        evidence_units=first.evidence_units,
    )
    assert compiler_input.registry == first.registry


def semver_uuid() -> UUID:
    """Return a stable snapshot identifier without obscuring assertions."""

    return RUN_ID


def test_feature_selection_runs_only_resolved_analyzer() -> None:
    selected = analyzers()[0].specification.supported_features[0]
    result = asyncio.run(engine().analyze(request(), features=(selected,)))

    assert len(result.execution_trace) == 1
    assert result.execution_trace[0].analyzer_id == "tier1.document_statistics"
    assert len(result.observations) == 5


def test_failures_are_isolated_and_failed_dependencies_are_skipped() -> None:
    good: ConfigurableAnalyzer
    bad = ConfigurableAnalyzer("bad", "test.bad", lambda _: RuntimeError("boom"))
    good = ConfigurableAnalyzer("good", "test.good", lambda context: one_candidate(context, good))
    dependent = ConfigurableAnalyzer(
        "dependent",
        "test.dependent",
        lambda context: one_candidate(context, dependent),
        dependencies=(AnalyzerDependency(analyzer_id="bad", minimum_version=semver()),),
    )
    result = asyncio.run(
        engine(
            (bad, good, dependent),
            feature_ids=("test.bad", "test.good", "test.dependent"),
        ).analyze(request())
    )

    statuses = {item.analyzer_id: item for item in result.execution_trace}
    assert result.status is AnalysisRunStatus.PARTIAL
    assert len(result.observations) == 1
    assert statuses["bad"].status is AnalyzerRunStatus.FAILED
    assert statuses["bad"].error_code == "analyzer_execution_error"
    assert statuses["dependent"].status is AnalyzerRunStatus.SKIPPED
    assert statuses["dependent"].error_code == "dependency_failed"
    assert statuses["good"].status is AnalyzerRunStatus.SUCCEEDED


def test_invalid_analyzer_output_isolated_at_builder_boundary() -> None:
    invalid: ConfigurableAnalyzer
    invalid = ConfigurableAnalyzer(
        "invalid",
        "test.invalid",
        lambda context: (
            MeasurementCandidate(
                feature=feature_definition("test.undeclared").reference,
                value=ScalarValue(value=1, unit="count"),
                evidence_span_ids=(context.analyzed_document.document_span.id,),
                opportunity_count=1,
            ),
        ),
    )
    result = asyncio.run(engine((invalid,), feature_ids=("test.invalid",)).analyze(request()))

    assert result.status is AnalysisRunStatus.FAILED
    assert result.observations == ()
    assert result.execution_trace[0].status is AnalyzerRunStatus.FAILED
    assert result.execution_trace[0].error_code == "observation_build_error"


class MemoryCache:
    """Observable in-memory implementation of the future cache port."""

    def __init__(self) -> None:
        self.values: dict[str, tuple[MeasurementCandidate, ...]] = {}

    async def get(self, key: str) -> tuple[MeasurementCandidate, ...] | None:
        return self.values.get(key)

    async def put(self, key: str, value: tuple[MeasurementCandidate, ...]) -> None:
        self.values[key] = value


class Metrics:
    """Observable metrics sink kept outside deterministic output."""

    def __init__(self) -> None:
        self.records: list[tuple[str, float, bool]] = []

    def record(self, *, analyzer_id: str, duration_seconds: float, succeeded: bool) -> None:
        self.records.append((analyzer_id, duration_seconds, succeeded))


class FailingMetrics:
    """Metrics adapter failure used to verify telemetry isolation."""

    def record(self, *, analyzer_id: str, duration_seconds: float, succeeded: bool) -> None:
        del analyzer_id, duration_seconds, succeeded
        raise RuntimeError("telemetry unavailable")


def test_cache_and_metrics_hooks_preserve_observation_determinism() -> None:
    cache = MemoryCache()
    metrics = Metrics()
    configured = engine(cache=cache, metrics=metrics)

    first = asyncio.run(configured.analyze(request()))
    second = asyncio.run(configured.analyze(request()))

    assert first.observations == second.observations
    assert first.evidence_units == second.evidence_units
    assert all(item.status is AnalyzerRunStatus.CACHE_HIT for item in second.execution_trace)
    assert len(cache.values) == 7
    assert len(metrics.records) == 14
    assert all(duration >= 0 for _, duration, _ in metrics.records)
    assert all(succeeded for _, _, succeeded in metrics.records)


def test_metrics_failure_does_not_change_domain_success() -> None:
    result = asyncio.run(engine(metrics=FailingMetrics()).analyze(request()))

    assert result.status is AnalysisRunStatus.SUCCEEDED
    assert len(result.observations) == 38


def test_independent_analyzers_execute_concurrently() -> None:
    entered: list[str] = []
    both_entered = asyncio.Event()

    async def wait_for_peer(
        name: str, context: AnalyzerContext, analyzer: Analyzer
    ) -> tuple[MeasurementCandidate, ...]:
        entered.append(name)
        if len(entered) == 2:
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=0.2)
        return one_candidate(context, analyzer)

    left: ConfigurableAnalyzer
    right: ConfigurableAnalyzer
    left = ConfigurableAnalyzer(
        "left", "test.left", lambda context: wait_for_peer("left", context, left)
    )
    right = ConfigurableAnalyzer(
        "right", "test.right", lambda context: wait_for_peer("right", context, right)
    )

    result = asyncio.run(
        engine((left, right), feature_ids=("test.left", "test.right")).analyze(request())
    )

    assert entered == ["left", "right"]
    assert result.status is AnalysisRunStatus.SUCCEEDED
    assert {item.level for item in result.execution_trace} == {0}
