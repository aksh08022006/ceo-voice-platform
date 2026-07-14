"""Observation construction, confidence dispatch, and integrity validation tests."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.analysis import (
    AnalysisRequest,
    AnalyzedDocument,
    AnalyzerSpecification,
    ComposedConfidence,
    ConfidenceComposerRegistry,
    ConfidenceMethod,
    ConfidenceRequest,
    DeclaredConfidenceComposer,
    DeterministicDocumentAnalyzer,
    MeasurementCandidate,
    ObservationBuilder,
)
from ceo_voice.analysis.contracts import ObservationSet
from ceo_voice.core.exceptions import ObservationBuildError
from ceo_voice.models.enums import Platform
from ceo_voice.voice import (
    AggregationStrategyReference,
    EvidenceUnitType,
    EvidenceWeightComponents,
    FeatureValueType,
    MeasurementClass,
    ScalarValue,
    SourceModality,
)
from tests.unit.analysis.factories import (
    CONFIG_HASH,
    NOW,
    RUN_ID,
    clean_document,
    confidence_composer,
    feature_definition,
    identity,
    registry,
    semver,
)
from tests.unit.analysis.test_registry_contracts import specification


def builder_subject(
    feature_id: str = "test.builder",
) -> tuple[
    ObservationBuilder,
    AnalysisRequest,
    AnalyzedDocument,
    AnalyzerSpecification,
    MeasurementCandidate,
]:
    """Return complete builder fixtures for one document-scoped feature."""

    definition = feature_definition(feature_id)
    selected_registry = registry(feature_ids=(feature_id,))
    request = AnalysisRequest(
        run_id=RUN_ID,
        document=clean_document(),
        voice_identity=identity(),
        source_modality=SourceModality.AUTHORED_WRITTEN,
        event_time=NOW,
        created_at=NOW,
    )
    analyzed = DeterministicDocumentAnalyzer(segmentation_version=semver()).analyze(
        request.document
    )
    analyzer = specification("builder", feature_id)
    candidate = MeasurementCandidate(
        feature=definition.reference,
        value=ScalarValue(value=2, unit="count"),
        evidence_span_ids=(
            analyzed.document_span.id,
            analyzed.paragraphs[0].id,
            analyzed.sentences[0].id,
        ),
        opportunity_count=2,
    )
    builder = ObservationBuilder(
        feature_registry=selected_registry,
        confidence_composer=confidence_composer(),
    )
    return builder, request, analyzed, analyzer, candidate


def test_builder_creates_complete_traceable_observation_and_evidence() -> None:
    builder, request, analyzed, analyzer, candidate = builder_subject()
    observation, evidence = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=0,
    )

    assert observation.feature == candidate.feature
    assert observation.voice_identity_id == request.voice_identity.id
    assert observation.context.platform is Platform.LINKEDIN
    assert observation.quality == 1
    assert observation.producer.configuration_hash == CONFIG_HASH
    assert tuple(reference.evidence_unit_id for reference in observation.evidence) == tuple(
        unit.id for unit in evidence
    )
    assert all(unit.document_id == request.document.id for unit in evidence)
    assert evidence[1].structural_position and "paragraph:" in evidence[1].structural_position
    assert evidence[2].structural_position and "sentence:" in evidence[2].structural_position


def test_builder_ids_are_repeatable_and_candidate_ordinals_are_distinct() -> None:
    builder, request, analyzed, analyzer, candidate = builder_subject()
    first, _ = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=0,
    )
    repeated, _ = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=0,
    )
    distinct, _ = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=1,
    )
    assert first == repeated
    assert first.id != distinct.id


def test_builder_rejects_undeclared_missing_registry_and_unknown_evidence() -> None:
    builder, request, analyzed, analyzer, candidate = builder_subject()
    undeclared = candidate.model_copy(
        update={"feature": feature_definition("test.undeclared").reference}
    )
    with pytest.raises(ObservationBuildError, match="undeclared"):
        builder.build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=undeclared,
            candidate_ordinal=0,
        )

    absent_builder = ObservationBuilder(
        feature_registry=registry(feature_ids=("test.other",)),
        confidence_composer=confidence_composer(),
    )
    with pytest.raises(ObservationBuildError, match="absent"):
        absent_builder.build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=candidate,
            candidate_ordinal=0,
        )

    unknown = candidate.model_copy(update={"evidence_span_ids": (UUID(int=999),)})
    with pytest.raises(ObservationBuildError, match="unknown evidence"):
        builder.build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=unknown,
            candidate_ordinal=0,
        )


def test_builder_rejects_registry_measurement_value_modality_and_scope_mismatches() -> None:
    _, request, analyzed, analyzer, candidate = builder_subject()
    base = feature_definition("test.builder")

    statistical_payload = base.model_dump()
    statistical_payload["measurement_pipeline"] = (MeasurementClass.STATISTICAL,)
    statistical = type(base).model_validate(statistical_payload)
    with pytest.raises(ObservationBuildError, match="measurement"):
        ObservationBuilder(
            feature_registry=type(registry()).build(
                registry_id=UUID(int=555),
                version=semver(),
                definitions=(statistical,),
                created_at=NOW,
            ),
            confidence_composer=confidence_composer(),
        ).build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=candidate,
            candidate_ordinal=0,
        )

    value_payload = base.model_dump()
    value_payload["value_type"] = FeatureValueType.INTERVAL
    value_payload["aggregation_strategy"] = AggregationStrategyReference(
        strategy_id="aggregation.interval",
        version=semver(),
        output_value_type=FeatureValueType.INTERVAL,
    )
    interval_definition = type(base).model_validate(value_payload)
    with pytest.raises(ObservationBuildError, match="value type"):
        ObservationBuilder(
            feature_registry=type(registry()).build(
                registry_id=UUID(int=556),
                version=semver(),
                definitions=(interval_definition,),
                created_at=NOW,
            ),
            confidence_composer=confidence_composer(),
        ).build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=candidate,
            candidate_ordinal=0,
        )

    modality_payload = base.model_dump()
    modality_payload["supported_modalities"] = (SourceModality.PREPARED_SPOKEN,)
    evidence_requirements = dict(modality_payload["evidence_requirements"])
    evidence_requirements["allowed_modalities"] = (SourceModality.PREPARED_SPOKEN,)
    modality_payload["evidence_requirements"] = evidence_requirements
    modality_definition = type(base).model_validate(modality_payload)
    with pytest.raises(ObservationBuildError, match="modality"):
        ObservationBuilder(
            feature_registry=type(registry()).build(
                registry_id=UUID(int=557),
                version=semver(),
                definitions=(modality_definition,),
                created_at=NOW,
            ),
            confidence_composer=confidence_composer(),
        ).build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=candidate,
            candidate_ordinal=0,
        )

    sentence_payload = base.model_dump()
    sentence_payload["observation_scope"] = EvidenceUnitType.SENTENCE
    sentence_definition = type(base).model_validate(sentence_payload)
    document_only = candidate.model_copy(update={"evidence_span_ids": (analyzed.document_span.id,)})
    with pytest.raises(ObservationBuildError, match="scope"):
        ObservationBuilder(
            feature_registry=type(registry()).build(
                registry_id=UUID(int=558),
                version=semver(),
                definitions=(sentence_definition,),
                created_at=NOW,
            ),
            confidence_composer=confidence_composer(),
        ).build(
            request=request,
            analyzed_document=analyzed,
            analyzer=analyzer,
            candidate=document_only,
            candidate_ordinal=0,
        )


def test_confidence_registry_dispatches_all_methods_and_rejects_missing_method() -> None:
    result = ComposedConfidence(
        quality=0.9,
        evidence_weights=EvidenceWeightComponents(
            target_attribution=1,
            speaker_attribution=1,
            source_reliability=1,
            modality_admissibility=1,
            observation_quality=0.9,
            independence=1,
            context_relevance=1,
            temporal_relevance=1,
            rights_admissible=True,
        ),
    )
    composer = DeclaredConfidenceComposer(result)
    dispatch = ConfidenceComposerRegistry(dict.fromkeys(ConfidenceMethod, composer))
    _, _, _, analyzer, candidate = builder_subject()

    for method in ConfidenceMethod:
        request = ConfidenceRequest(
            method=method,
            measurement_class=MeasurementClass.DETERMINISTIC,
            analyzer=analyzer,
            candidate=candidate,
            evidence_count=1,
        )
        assert dispatch.compose(request) == result

    missing = ConfidenceComposerRegistry({})
    with pytest.raises(ObservationBuildError, match="no registered"):
        missing.compose(request)


def test_observation_set_rejects_duplicate_noncanonical_dangling_and_wrong_ownership() -> None:
    builder, request, analyzed, analyzer, candidate = builder_subject()
    first, evidence = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=0,
    )
    second, _ = builder.build(
        request=request,
        analyzed_document=analyzed,
        analyzer=analyzer,
        candidate=candidate,
        candidate_ordinal=1,
    )
    ordered_observations = tuple(sorted((first, second), key=lambda item: item.id.int))
    base: dict[str, object] = {
        "run_id": RUN_ID,
        "tenant_id": request.document.tenant_id,
        "voice_identity_id": request.voice_identity.id,
        "document_id": request.document.id,
        "document_version": 1,
        "registry": registry(feature_ids=("test.builder",)).reference,
        "status": "succeeded",
        "observations": ordered_observations,
        "evidence_units": tuple(sorted(evidence, key=lambda item: item.id.int)),
        "execution_trace": (),
        "created_at": NOW,
    }
    assert ObservationSet.model_validate(base).to_evidence_snapshot(snapshot_id=RUN_ID)

    for update, message in (
        ({"observations": (first, first)}, "identifiers"),
        ({"observations": tuple(reversed(ordered_observations))}, "canonical"),
        ({"evidence_units": (evidence[0], evidence[0])}, "evidence-unit"),
        ({"evidence_units": ()}, "dangling"),
        (
            {"observations": (first.model_copy(update={"tenant_id": UUID(int=999)}),)},
            "tenant",
        ),
        (
            {"observations": (first.model_copy(update={"voice_identity_id": UUID(int=999)}),)},
            "identity",
        ),
    ):
        payload = dict(base)
        payload.update(update)
        with pytest.raises(ValidationError, match=message):
            ObservationSet.model_validate(payload)
