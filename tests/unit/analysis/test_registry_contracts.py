"""Analyzer registry, dependency graph, and boundary-contract tests."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.analysis import (
    AddressedSpan,
    AnalysisRequest,
    AnalyzerCategory,
    AnalyzerDependency,
    AnalyzerInput,
    AnalyzerRegistry,
    AnalyzerSpecification,
    MeasurementCandidate,
)
from ceo_voice.analysis.enums import AnalyzerRunStatus
from ceo_voice.core.exceptions import AnalyzerDependencyError, AnalyzerRegistrationError
from ceo_voice.models.enums import Platform
from ceo_voice.voice import (
    EvidenceUnitType,
    MeasurementClass,
    ObservationState,
    ScalarValue,
    SourceModality,
)
from tests.unit.analysis.factories import (
    CONFIG_HASH,
    NOW,
    RUN_ID,
    clean_document,
    feature_definition,
    identity,
    semver,
)


class StubAnalyzer:
    """Minimal analyzer used to exercise registry behavior."""

    def __init__(self, specification: AnalyzerSpecification) -> None:
        self._specification = specification

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: object) -> tuple[MeasurementCandidate, ...]:
        del context
        return ()


def specification(
    analyzer_id: str,
    feature_id: str,
    *,
    version: str = "1.0.0",
    dependencies: tuple[AnalyzerDependency, ...] = (),
    all_platforms: bool = True,
    platforms: tuple[Platform, ...] = (),
    all_languages: bool = True,
    languages: tuple[str, ...] = (),
    priority: int = 100,
) -> AnalyzerSpecification:
    """Return a complete analyzer specification."""

    return AnalyzerSpecification(
        analyzer_id=analyzer_id,
        version=semver(version),
        category=AnalyzerCategory.FORMATTING,
        supported_features=(feature_definition(feature_id).reference,),
        required_inputs=(AnalyzerInput.DOCUMENT,),
        all_platforms=all_platforms,
        supported_platforms=platforms,
        all_languages=all_languages,
        supported_languages=languages,
        priority=priority,
        measurement_class=MeasurementClass.DETERMINISTIC,
        dependencies=dependencies,
        configuration_hash=CONFIG_HASH,
    )


def test_registry_registration_lookup_and_feature_resolution_are_immutable() -> None:
    first = StubAnalyzer(specification("first", "test.first"))
    second = StubAnalyzer(specification("second", "test.second", priority=10))
    original = AnalyzerRegistry((first,))
    evolved = original.register(second)

    assert original.analyzers == (first,)
    assert evolved.analyzers == (second, first)
    assert evolved.get("first") is first
    assert evolved.resolve_feature(second.specification.supported_features[0]) is second
    with pytest.raises(AnalyzerRegistrationError, match="not registered"):
        evolved.get("missing")
    with pytest.raises(AnalyzerRegistrationError, match="no analyzer"):
        evolved.resolve_feature(feature_definition("test.missing").reference)


def test_registry_rejects_duplicate_ids_and_feature_conflicts() -> None:
    first = StubAnalyzer(specification("same", "test.first"))
    duplicate_id = StubAnalyzer(specification("same", "test.second"))
    duplicate_feature = StubAnalyzer(specification("other", "test.first"))

    with pytest.raises(AnalyzerRegistrationError, match="identifier"):
        AnalyzerRegistry((first, duplicate_id))
    with pytest.raises(AnalyzerRegistrationError, match="conflicting"):
        AnalyzerRegistry((first, duplicate_feature))


def test_dependency_plan_creates_priority_sorted_parallel_levels_and_closure() -> None:
    base = StubAnalyzer(specification("base", "test.base", priority=50))
    sibling = StubAnalyzer(specification("sibling", "test.sibling", priority=1))
    dependent = StubAnalyzer(
        specification(
            "dependent",
            "test.dependent",
            dependencies=(AnalyzerDependency(analyzer_id="base", minimum_version=semver()),),
        )
    )
    registry = AnalyzerRegistry((dependent, base, sibling))

    full_plan = registry.plan(document=clean_document())
    selected_plan = registry.plan(
        document=clean_document(), features=dependent.specification.supported_features
    )

    assert tuple(item.specification.analyzer_id for item in full_plan[0]) == ("sibling", "base")
    assert tuple(item.specification.analyzer_id for item in full_plan[1]) == ("dependent",)
    assert tuple(item.specification.analyzer_id for item in selected_plan[0]) == ("base",)
    assert tuple(item.specification.analyzer_id for item in selected_plan[1]) == ("dependent",)


def test_dependency_plan_rejects_missing_incompatible_and_cyclic_dependencies() -> None:
    missing = StubAnalyzer(
        specification(
            "missing-user",
            "test.missing-user",
            dependencies=(AnalyzerDependency(analyzer_id="absent", minimum_version=semver()),),
        )
    )
    with pytest.raises(AnalyzerRegistrationError, match="not registered"):
        AnalyzerRegistry((missing,)).plan(document=clean_document())

    base = StubAnalyzer(specification("base", "test.base", version="1.0.0"))
    incompatible = StubAnalyzer(
        specification(
            "new-user",
            "test.new-user",
            dependencies=(AnalyzerDependency(analyzer_id="base", minimum_version=semver("2.0.0")),),
        )
    )
    with pytest.raises(AnalyzerDependencyError, match="version"):
        AnalyzerRegistry((base, incompatible)).plan(document=clean_document())

    left = StubAnalyzer(
        specification(
            "left",
            "test.left",
            dependencies=(AnalyzerDependency(analyzer_id="right", minimum_version=semver()),),
        )
    )
    right = StubAnalyzer(
        specification(
            "right",
            "test.right",
            dependencies=(AnalyzerDependency(analyzer_id="left", minimum_version=semver()),),
        )
    )
    with pytest.raises(AnalyzerDependencyError, match="cycle"):
        AnalyzerRegistry((left, right)).plan(document=clean_document())


def test_dependency_version_bounds_and_document_scope() -> None:
    constraint = AnalyzerDependency(
        analyzer_id="base", minimum_version=semver("1.2.0"), maximum_major=2
    )
    assert not constraint.accepts(semver("1.1.9"))
    assert constraint.accepts(semver("2.0.0"))
    assert not constraint.accepts(semver("3.0.0"))

    scoped = StubAnalyzer(
        specification(
            "scoped",
            "test.scoped",
            all_platforms=False,
            platforms=(Platform.X,),
            all_languages=False,
            languages=("fr",),
        )
    )
    assert AnalyzerRegistry((scoped,)).plan(document=clean_document()) == ()
    with pytest.raises(AnalyzerDependencyError, match="incompatible"):
        AnalyzerRegistry((scoped,)).plan(
            document=clean_document(), features=scoped.specification.supported_features
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"supported_features": (feature_definition("test.x").reference,) * 2}, "features"),
        ({"required_inputs": (AnalyzerInput.DOCUMENT,) * 2}, "inputs"),
        ({"all_platforms": True, "supported_platforms": (Platform.X,)}, "platform"),
        ({"all_platforms": False, "supported_platforms": ()}, "platform"),
        ({"all_languages": True, "supported_languages": ("en",)}, "language"),
        ({"all_languages": False, "supported_languages": ()}, "language"),
        (
            {
                "dependencies": (
                    AnalyzerDependency(analyzer_id="dep", minimum_version=semver()),
                    AnalyzerDependency(analyzer_id="dep", minimum_version=semver()),
                )
            },
            "dependencies",
        ),
        (
            {"dependencies": (AnalyzerDependency(analyzer_id="base", minimum_version=semver()),)},
            "itself",
        ),
    ],
)
def test_analyzer_specification_rejects_ambiguous_capabilities(
    updates: dict[str, object], message: str
) -> None:
    payload = specification("base", "test.base").model_dump()
    payload.update(updates)
    with pytest.raises(ValidationError, match=message):
        AnalyzerSpecification.model_validate(payload)


def test_analysis_request_and_candidate_validate_ownership_value_and_evidence() -> None:
    request = AnalysisRequest(
        run_id=RUN_ID,
        document=clean_document(),
        voice_identity=identity(),
        source_modality=SourceModality.AUTHORED_WRITTEN,
        event_time=NOW,
        created_at=NOW,
    )
    assert request.document.ceo_id == request.voice_identity.leader_id

    wrong_identity = identity().model_dump()
    wrong_identity["leader_id"] = UUID(int=999)
    with pytest.raises(ValidationError, match="leader"):
        AnalysisRequest(
            run_id=RUN_ID,
            document=clean_document(),
            voice_identity=type(identity()).model_validate(wrong_identity),
            source_modality=SourceModality.AUTHORED_WRITTEN,
            event_time=NOW,
            created_at=NOW,
        )

    feature = feature_definition("test.candidate").reference
    with pytest.raises(ValidationError, match="require a value"):
        MeasurementCandidate(
            feature=feature,
            value=None,
            evidence_span_ids=(RUN_ID,),
            opportunity_count=1,
        )
    with pytest.raises(ValidationError, match="cannot contain"):
        MeasurementCandidate(
            feature=feature,
            state=ObservationState.MISSING,
            value=ScalarValue(value=1, unit="count"),
            evidence_span_ids=(RUN_ID,),
            opportunity_count=1,
        )
    with pytest.raises(ValidationError, match="unique"):
        MeasurementCandidate(
            feature=feature,
            value=ScalarValue(value=1, unit="count"),
            evidence_span_ids=(RUN_ID, RUN_ID),
            opportunity_count=1,
        )


def test_addressed_span_validates_offsets_and_structural_identity() -> None:
    with pytest.raises(ValidationError, match="greater"):
        AddressedSpan(
            id=RUN_ID,
            unit_type=EvidenceUnitType.DOCUMENT,
            start_offset=2,
            end_offset=2,
            ordinal=0,
        )
    with pytest.raises(ValidationError, match="sentence spans"):
        AddressedSpan(
            id=RUN_ID,
            unit_type=EvidenceUnitType.SENTENCE,
            start_offset=0,
            end_offset=2,
            ordinal=0,
            sentence_id=UUID(int=2),
        )
    with pytest.raises(ValidationError, match="paragraph spans"):
        AddressedSpan(
            id=RUN_ID,
            unit_type=EvidenceUnitType.PARAGRAPH,
            start_offset=0,
            end_offset=2,
            ordinal=0,
            paragraph_id=UUID(int=2),
        )

    assert AnalyzerRunStatus.SUCCEEDED.value == "succeeded"
