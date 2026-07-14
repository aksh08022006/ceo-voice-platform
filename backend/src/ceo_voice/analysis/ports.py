"""Dependency-inverted ports for analyzers, confidence, caching, and telemetry."""

from typing import Protocol, runtime_checkable

from ceo_voice.analysis.contracts import (
    AnalyzerContext,
    AnalyzerSpecification,
    ComposedConfidence,
    ConfidenceRequest,
    MeasurementCandidate,
)


@runtime_checkable
class Analyzer(Protocol):
    """Pure, independently registered feature analyzer."""

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return declarative execution and compatibility metadata."""

        ...

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return immutable candidates without constructing HVM observations."""

        ...


@runtime_checkable
class ConfidenceComposer(Protocol):
    """Compose complete confidence without prescribing an estimation algorithm."""

    def compose(self, request: ConfidenceRequest) -> ComposedConfidence:
        """Return HVM-compatible quality and decomposed evidence weights."""

        ...


@runtime_checkable
class AnalyzerResultCache(Protocol):
    """Optional future cache hook keyed by immutable analysis inputs."""

    async def get(self, key: str) -> tuple[MeasurementCandidate, ...] | None:
        """Return cached candidates or ``None``."""

        ...

    async def put(self, key: str, value: tuple[MeasurementCandidate, ...]) -> None:
        """Store immutable candidates for later equivalent runs."""

        ...


@runtime_checkable
class ExecutionMetricsSink(Protocol):
    """Out-of-band operational metrics excluded from deterministic domain output."""

    def record(self, *, analyzer_id: str, duration_seconds: float, succeeded: bool) -> None:
        """Record one analyzer execution measurement."""

        ...
