"""Instance-scoped analyzer registration, resolution, and dependency planning."""

from collections.abc import Iterable

from ceo_voice.analysis.contracts import AnalyzerSpecification
from ceo_voice.analysis.ports import Analyzer
from ceo_voice.core.exceptions import AnalyzerDependencyError, AnalyzerRegistrationError
from ceo_voice.ingestion import CleanDocument
from ceo_voice.voice.primitives import FeatureReference


class AnalyzerRegistry:
    """Immutable analyzer catalog with no process-global discovery state."""

    def __init__(self, analyzers: Iterable[Analyzer] = ()) -> None:
        ordered = tuple(
            sorted(
                analyzers,
                key=lambda item: (
                    item.specification.priority,
                    item.specification.analyzer_id,
                    str(item.specification.version),
                ),
            )
        )
        self._validate(ordered)
        self._analyzers = ordered
        self._by_id = {item.specification.analyzer_id: item for item in ordered}
        self._by_feature = {
            feature: item for item in ordered for feature in item.specification.supported_features
        }

    @property
    def analyzers(self) -> tuple[Analyzer, ...]:
        """Return analyzers in canonical dispatch order."""

        return self._analyzers

    def register(self, analyzer: Analyzer) -> "AnalyzerRegistry":
        """Return a new registry containing ``analyzer``."""

        return AnalyzerRegistry((*self._analyzers, analyzer))

    def get(self, analyzer_id: str) -> Analyzer:
        """Resolve a stable analyzer identifier."""

        try:
            return self._by_id[analyzer_id]
        except KeyError as exc:
            raise AnalyzerRegistrationError(
                "analyzer was not registered", details={"analyzer_id": analyzer_id}
            ) from exc

    def resolve_feature(self, feature: FeatureReference) -> Analyzer:
        """Resolve the unique analyzer for an exact feature definition."""

        try:
            return self._by_feature[feature]
        except KeyError as exc:
            raise AnalyzerRegistrationError(
                "no analyzer supports the requested feature",
                details={"feature_id": feature.feature_id, "version": str(feature.version)},
            ) from exc

    def plan(
        self,
        *,
        document: CleanDocument,
        features: tuple[FeatureReference, ...] | None = None,
    ) -> tuple[tuple[Analyzer, ...], ...]:
        """Build deterministic parallel execution levels including dependency closure."""

        roots = (
            tuple(self.resolve_feature(feature) for feature in features)
            if features is not None
            else tuple(item for item in self._analyzers if item.specification.supports(document))
        )
        selected: dict[str, Analyzer] = {}

        def include(analyzer: Analyzer) -> None:
            specification = analyzer.specification
            if specification.analyzer_id in selected:
                return
            if not specification.supports(document):
                raise AnalyzerDependencyError(
                    "analyzer is incompatible with the document context",
                    details={"analyzer_id": specification.analyzer_id},
                )
            selected[specification.analyzer_id] = analyzer
            for dependency in specification.dependencies:
                dependency_analyzer = self.get(dependency.analyzer_id)
                if not dependency.accepts(dependency_analyzer.specification.version):
                    raise AnalyzerDependencyError(
                        "analyzer dependency version is incompatible",
                        details={
                            "analyzer_id": specification.analyzer_id,
                            "dependency_id": dependency.analyzer_id,
                            "installed_version": str(dependency_analyzer.specification.version),
                        },
                    )
                include(dependency_analyzer)

        for root in roots:
            include(root)

        pending = dict(selected)
        completed: set[str] = set()
        levels: list[tuple[Analyzer, ...]] = []
        while pending:
            ready = tuple(
                analyzer
                for analyzer in pending.values()
                if all(
                    dependency.analyzer_id in completed
                    for dependency in analyzer.specification.dependencies
                )
            )
            if not ready:
                raise AnalyzerDependencyError(
                    "analyzer dependency graph contains a cycle",
                    details={"analyzer_ids": sorted(pending)},
                )
            ordered = tuple(
                sorted(
                    ready,
                    key=lambda item: (
                        item.specification.priority,
                        item.specification.analyzer_id,
                    ),
                )
            )
            levels.append(ordered)
            for analyzer in ordered:
                analyzer_id = analyzer.specification.analyzer_id
                completed.add(analyzer_id)
                del pending[analyzer_id]
        return tuple(levels)

    @staticmethod
    def _validate(analyzers: tuple[Analyzer, ...]) -> None:
        ids: dict[str, AnalyzerSpecification] = {}
        features: dict[FeatureReference, str] = {}
        for analyzer in analyzers:
            specification = analyzer.specification
            if specification.analyzer_id in ids:
                raise AnalyzerRegistrationError(
                    "analyzer identifier is already registered",
                    details={"analyzer_id": specification.analyzer_id},
                )
            ids[specification.analyzer_id] = specification
            for feature in specification.supported_features:
                if feature in features:
                    raise AnalyzerRegistrationError(
                        "feature has conflicting analyzer registrations",
                        details={
                            "feature_id": feature.feature_id,
                            "analyzers": (features[feature], specification.analyzer_id),
                        },
                    )
                features[feature] = specification.analyzer_id
