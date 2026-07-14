"""Behavior tests for structural validation and interface-driven profile compilation."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.core.exceptions import HVMValidationError, ProfileCompilationError
from ceo_voice.models.enums import Platform
from ceo_voice.voice import (
    Aggregate,
    AggregationRequest,
    CompilationRequest,
    ConditionalResidual,
    ConditionalResidualEstimationRequest,
    ConfidenceEstimationRequest,
    ConstraintBasis,
    ConstraintSeverity,
    CopyRisk,
    DecisionState,
    DriftEstimationRequest,
    DriftState,
    EvidenceRequirements,
    EvidenceRole,
    ExplicitPreference,
    FeatureDefinition,
    HVMRelease,
    Interaction,
    InteractionEstimationRequest,
    InteractionType,
    IntervalValue,
    MeasurementClass,
    NegativeConstraint,
    PartialPoolingRequest,
    PreferenceAuthority,
    ProfileCompiler,
    ProfileComponents,
    Prototype,
    PrototypeKind,
    ReleaseValidationSubject,
    Residual,
    ResidualComputationRequest,
    ScalarValue,
    SemanticVersion,
    SourceModality,
    StructuralReleaseValidator,
    TimeRange,
    ValidationCode,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    VoiceContext,
)
from tests.unit.voice.factories import (
    ACTOR_ID,
    BUILD_ID,
    EVIDENCE_ID,
    IDENTITY_ID,
    NOW,
    OBSERVATION_ID,
    RELEASE_ID,
    REPORT_ID,
    RESIDUAL_ID,
    TENANT_ID,
    aggregate,
    confidence,
    context,
    evidence_reference,
    evidence_snapshot,
    evidence_unit,
    feature_definition,
    identity,
    lineage,
    observation,
    registry,
    release,
    residual,
    semver,
)


def validation_subject(*, release_value: HVMRelease | None = None) -> ReleaseValidationSubject:
    """Return a complete valid validation subject."""

    return ReleaseValidationSubject(
        identity=identity(),
        lineage=lineage(),
        release=release_value or release(),
        evidence_snapshot=evidence_snapshot(),
        evidence_units=(evidence_unit(),),
        observations=(observation(),),
    )


def compilation_request() -> CompilationRequest:
    """Return one complete deterministic compiler request."""

    return CompilationRequest(
        build_id=BUILD_ID,
        release_id=RELEASE_ID,
        release_version=1,
        validation_report_id=REPORT_ID,
        identity=identity(),
        lineage=lineage(),
        evidence_snapshot=evidence_snapshot(),
        evidence_units=(evidence_unit(),),
        observations=(observation(),),
        created_at=NOW,
        validated_at=NOW,
    )


def test_structural_validator_accepts_complete_reference_graph() -> None:
    validator = StructuralReleaseValidator(registry=registry(), version=semver())
    subject = validation_subject()

    report = validator.validate(subject, report_id=REPORT_ID, validated_at=NOW)

    assert report.is_valid()
    assert report.issues == ()
    assert report.release_content_hash == subject.release.content_hash


def test_structural_validator_detects_observation_content_tampering() -> None:
    validator = StructuralReleaseValidator(registry=registry(), version=semver())
    changed = observation().model_copy(update={"quality": 0.1})
    subject = validation_subject().model_copy(update={"observations": (changed,)})

    report = validator.validate(subject, report_id=REPORT_ID, validated_at=NOW)

    assert any("release-pinned reference" in issue.message for issue in report.issues)


def test_structural_validator_reports_registry_manifest_and_version_mismatches() -> None:
    validator = StructuralReleaseValidator(registry=registry(), version=semver())
    valid = release()
    mismatched = valid.model_copy(
        update={
            "registry": valid.registry.model_copy(update={"snapshot_hash": "f" * 64}),
            "evidence_snapshot": valid.evidence_snapshot.model_copy(
                update={"snapshot_hash": "e" * 64}
            ),
            "version": 2,
            "previous_release_id": UUID(int=999),
        }
    )

    report = validator.validate(
        validation_subject(release_value=mismatched), report_id=REPORT_ID, validated_at=NOW
    )

    assert not report.is_valid()
    assert {issue.code for issue in report.issues} >= {
        ValidationCode.VERSION_CONSISTENCY,
    }
    assert any(issue.path == "release.registry" for issue in report.issues)
    assert any(issue.path == "release.evidence_snapshot" for issue in report.issues)
    assert any(issue.path == "previous_release" for issue in report.issues)


def test_structural_validator_reports_evidence_and_observation_orphans() -> None:
    validator = StructuralReleaseValidator(registry=registry(), version=semver())
    unknown_evidence = UUID(int=800)
    bad_observation = observation().model_copy(
        update={
            "evidence": (
                observation().evidence[0].model_copy(update={"evidence_unit_id": unknown_evidence}),
            )
        }
    )
    bad_release = release().model_copy(
        update={
            "observation_references": (bad_observation.reference,),
            "components": ProfileComponents(
                aggregates=(
                    aggregate().model_copy(
                        update={
                            "observation_ids": (UUID(int=801),),
                            "evidence_unit_ids": (unknown_evidence,),
                            "confidence": aggregate().confidence.model_copy(
                                update={"evidence_count": 0, "independent_cluster_count": 0}
                            ),
                        }
                    ),
                ),
                residuals=(
                    residual().model_copy(
                        update={
                            "aggregate_id": UUID(int=802),
                            "evidence_unit_ids": (unknown_evidence,),
                            "confidence": residual().confidence.model_copy(
                                update={"evidence_count": 0, "independent_cluster_count": 0}
                            ),
                        }
                    ),
                ),
            ),
        }
    )
    subject = validation_subject(release_value=bad_release).model_copy(
        update={"observations": (bad_observation,)}
    )

    report = validator.validate(subject, report_id=REPORT_ID, validated_at=NOW)

    codes = {issue.code for issue in report.issues}
    assert ValidationCode.REFERENCE_INTEGRITY in codes
    assert ValidationCode.CONFIDENCE_COMPLETENESS in codes
    assert ValidationCode.EVIDENCE_COMPLETENESS in codes


def test_structural_validator_reports_unknown_features_and_wrong_value_types() -> None:
    validator = StructuralReleaseValidator(registry=registry(), version=semver())
    unknown_feature = observation().feature.model_copy(
        update={"feature_id": "lexical.unknown-rate"}
    )
    bad_observation = observation().model_copy(update={"feature": unknown_feature})
    bad_aggregate = aggregate().model_copy(
        update={
            "value": ScalarValue(value=1, unit="rate"),
            "aggregation_strategy": aggregate().aggregation_strategy.model_copy(
                update={"strategy_id": "wrong"}
            ),
        }
    )
    bad_release = release().model_copy(
        update={
            "components": ProfileComponents(aggregates=(bad_aggregate,), residuals=(residual(),))
        }
    )
    subject = validation_subject(release_value=bad_release).model_copy(
        update={"observations": (bad_observation,)}
    )

    report = validator.validate(subject, report_id=REPORT_ID, validated_at=NOW)

    assert any(issue.code is ValidationCode.FEATURE_REGISTRY_CONSISTENCY for issue in report.issues)
    assert any("aggregate strategy" in issue.message for issue in report.issues)


def test_structural_validator_reports_complete_cross_graph_failure_surface() -> None:
    """Exercise every cross-artifact gate with one deliberately corrupt read model.

    The invalid objects use ``model_copy`` intentionally: persistence can contain stale or
    corrupted records even though constructors reject them, and the structural validator is the
    boundary responsible for reporting all such problems without failing fast.
    """

    base_definition = feature_definition()
    strict_definition = FeatureDefinition.model_validate(
        {
            **base_definition.model_dump(),
            "evidence_requirements": EvidenceRequirements(
                minimum_evidence_units=2,
                minimum_independent_clusters=2,
                required_roles=(EvidenceRole.SUPPORT, EvidenceRole.OPPORTUNITY),
                allowed_modalities=(SourceModality.AUTHORED_WRITTEN,),
                requires_target_attribution=True,
                requires_rights_admissibility=True,
            ),
        }
    )
    feature_registry = registry(definition=strict_definition)
    validator = StructuralReleaseValidator(registry=feature_registry, version=semver())
    unknown_id = UUID(int=880)
    unknown_feature = strict_definition.reference.model_copy(
        update={"feature_id": "lexical.unregistered-rate"}
    )
    unsupported_context = VoiceContext(language="fr", platform=Platform.X)
    wrong_value = IntervalValue(
        lower=0,
        upper=1,
        lower_inclusive=True,
        upper_inclusive=True,
        unit="range",
    )
    bad_confidence = confidence(evidence_count=0)
    bad_weights = evidence_reference().weight_components.model_copy(
        update={"target_attribution": 0, "rights_admissible": False}
    )
    bad_link = evidence_reference(role=EvidenceRole.COUNTEREVIDENCE).model_copy(
        update={"weight_components": bad_weights}
    )
    bad_observation = observation(definition=strict_definition).model_copy(
        update={
            "tenant_id": UUID(int=881),
            "measurement_class": MeasurementClass.LLM_DERIVED,
            "context": unsupported_context,
            "value": wrong_value,
            "evidence": (bad_link,),
        }
    )
    bad_unit = evidence_unit().model_copy(
        update={
            "tenant_id": UUID(int=882),
            "document_version": 2,
            "end_offset": 3,
            "source_modality": SourceModality.PREPARED_SPOKEN,
        }
    )
    extra_unit = evidence_unit(evidence_id=UUID(int=883))

    bad_aggregate = aggregate(definition=strict_definition).model_copy(
        update={
            "value": wrong_value,
            "context": unsupported_context,
            "observation_ids": (unknown_id,),
            "evidence_unit_ids": (unknown_id,),
            "aggregation_strategy": aggregate(
                definition=strict_definition
            ).aggregation_strategy.model_copy(update={"strategy_id": "aggregation.wrong"}),
            "confidence": bad_confidence,
        }
    )
    bad_residual = residual(definition=strict_definition).model_copy(
        update={
            "aggregate_id": unknown_id,
            "value": wrong_value,
            "context": unsupported_context,
            "evidence_unit_ids": (unknown_id,),
            "confidence": bad_confidence,
        }
    )
    conditional = ConditionalResidual(
        id=UUID(int=884),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=strict_definition.reference,
        parent_residual_id=RESIDUAL_ID,
        condition=context(),
        delta=ScalarValue(value=0.1, unit="residual"),
        transfer_confidence=0.8,
        evidence_unit_ids=(EVIDENCE_ID,),
        confidence=confidence(),
        decision_state=DecisionState.DESCRIPTIVE,
        created_at=NOW,
    ).model_copy(
        update={
            "parent_residual_id": unknown_id,
            "condition": unsupported_context,
            "delta": wrong_value,
            "evidence_unit_ids": (unknown_id,),
            "confidence": bad_confidence,
        }
    )
    interaction = Interaction(
        id=UUID(int=885),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        features=(strict_definition.reference, unknown_feature),
        interaction_type=InteractionType.CROSS_LAYER,
        context=context(),
        value=ScalarValue(value=0.2, unit="association"),
        evidence_unit_ids=(unknown_id,),
        confidence=bad_confidence,
        decision_state=DecisionState.EXPLORATORY,
        selection_policy_version="selection-1",
        created_at=NOW,
    )
    drift = DriftState(
        id=UUID(int=886),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        features=(unknown_feature,),
        status="candidate",
        candidate_regime="recent",
        comparison_range=TimeRange(starts_at=NOW),
        evidence_unit_ids=(unknown_id,),
        confidence=bad_confidence,
        created_at=NOW,
    )
    prototype = Prototype(
        id=UUID(int=887),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        kind=PrototypeKind.PROTOTYPE,
        evidence_unit_id=unknown_id,
        represented_features=(unknown_feature,),
        represented_interaction_ids=(unknown_id,),
        representativeness=0.8,
        diversity_cluster_id="prototype-cluster",
        copy_risk=CopyRisk.LOW,
        approved_by=ACTOR_ID,
        approved_at=NOW,
    )
    constraint = NegativeConstraint(
        id=UUID(int=888),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=strict_definition.reference,
        basis=ConstraintBasis.STATISTICAL_AVOIDANCE,
        severity=ConstraintSeverity.SOFT,
        scope=context(),
        prohibited_value=wrong_value,
        evidence=(evidence_reference(evidence_id=unknown_id),),
        effective_range=TimeRange(starts_at=NOW),
    )
    preference = ExplicitPreference(
        id=UUID(int=889),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=strict_definition.reference,
        target=wrong_value,
        scope=context(),
        authority=PreferenceAuthority.TARGET_LEADER,
        priority=50,
        tolerance=0.1,
        actor_id=ACTOR_ID,
        rationale_category="authenticity",
        effective_range=TimeRange(starts_at=NOW),
        created_at=NOW,
    )
    release_value = release(feature=strict_definition).model_copy(
        update={
            "observation_references": (
                observation(definition=strict_definition).reference.model_copy(
                    update={"observation_id": unknown_id}
                ),
            ),
            "components": ProfileComponents(
                aggregates=(bad_aggregate,),
                residuals=(bad_residual,),
                conditional_residuals=(conditional,),
                interactions=(interaction,),
                drift_states=(drift,),
            ),
            "prototypes": (prototype,),
            "negative_constraints": (constraint,),
            "explicit_preferences": (preference,),
        }
    )
    snapshot = evidence_snapshot()
    valid_subject = ReleaseValidationSubject(
        identity=identity(),
        lineage=lineage(),
        release=release(feature=strict_definition),
        evidence_snapshot=snapshot,
        evidence_units=(evidence_unit(),),
        observations=(observation(definition=strict_definition),),
    )
    corrupt_subject = valid_subject.model_copy(
        update={
            "identity": identity().model_copy(update={"tenant_id": UUID(int=890)}),
            "lineage": lineage().model_copy(
                update={"id": UUID(int=891), "voice_identity_id": UUID(int=892)}
            ),
            "release": release_value,
            "evidence_snapshot": snapshot.model_copy(update={"tenant_id": UUID(int=893)}),
            "evidence_units": (bad_unit, bad_unit, extra_unit),
            "observations": (bad_observation, bad_observation),
            "previous_release": release(feature=strict_definition),
        }
    )

    report = validator.validate(corrupt_subject, report_id=REPORT_ID, validated_at=NOW)

    paths = {issue.path for issue in report.issues}
    codes = {issue.code for issue in report.issues}
    assert len(report.issues) >= 30
    assert codes == set(ValidationCode)
    assert {"identity", "lineage", "evidence_snapshot", "lineage.id"} <= paths
    assert any(path.endswith("context.language") for path in paths)
    assert any(path.endswith("context.platform") for path in paths)
    assert any(path.startswith("prototypes.") for path in paths)
    assert any(path.startswith("negative_constraints.") for path in paths)
    assert any(path.startswith("explicit_preferences.") for path in paths)


def test_validation_subject_and_compilation_request_enforce_identity_boundaries() -> None:
    request = compilation_request()

    with pytest.raises(ValidationError, match="share a tenant"):
        CompilationRequest.model_validate(
            {
                **request.model_dump(),
                "lineage": request.lineage.model_copy(update={"tenant_id": UUID(int=999)}),
            }
        )
    with pytest.raises(ValidationError, match="unique IDs"):
        CompilationRequest.model_validate(
            {**request.model_dump(), "observations": request.observations * 2}
        )


class _Aggregator:
    def __init__(self, calls: list[str], output: tuple[Aggregate, ...]) -> None:
        self._calls = calls
        self._output = output

    def aggregate(self, request: AggregationRequest) -> tuple[Aggregate, ...]:
        assert request.build_id == BUILD_ID
        self._calls.append("aggregate")
        return self._output


class _Pooler:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def pool(self, request: PartialPoolingRequest) -> tuple[Aggregate, ...]:
        self._calls.append("pool")
        return request.aggregates


class _ResidualComputer:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def compute(self, request: ResidualComputationRequest) -> tuple[Residual, ...]:
        assert request.pooled_aggregates
        self._calls.append("residual")
        return (residual(),)


class _ConditionalEstimator:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def estimate(
        self, request: ConditionalResidualEstimationRequest
    ) -> tuple[ConditionalResidual, ...]:
        assert request.core_residuals
        self._calls.append("conditional")
        return ()


class _InteractionEstimator:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def estimate(self, request: InteractionEstimationRequest) -> tuple[Interaction, ...]:
        assert request.aggregates
        self._calls.append("interaction")
        return ()


class _DriftEstimator:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def estimate(self, request: DriftEstimationRequest) -> tuple[DriftState, ...]:
        assert request.residuals
        self._calls.append("drift")
        return ()


class _ConfidenceEstimator:
    def __init__(self, calls: list[str], *, tamper: bool = False) -> None:
        self._calls = calls
        self._tamper = tamper

    def estimate(self, request: ConfidenceEstimationRequest) -> ProfileComponents:
        self._calls.append("confidence")
        if not self._tamper:
            return request.components
        changed = request.components.aggregates[0].model_copy(
            update={"value": ScalarValue(value=9, unit="changed")}
        )
        return request.components.model_copy(update={"aggregates": (changed,)})


class _RejectingValidator:
    version = SemanticVersion.parse("1.0.0")

    def validate(
        self,
        subject: ReleaseValidationSubject,
        *,
        report_id: UUID,
        validated_at: object,
    ) -> ValidationReport:
        return ValidationReport(
            id=report_id,
            release_id=subject.release.id,
            release_content_hash=subject.release.content_hash,
            validator_version=self.version,
            issues=(
                ValidationIssue(
                    code=ValidationCode.REFERENCE_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    path="release",
                    message="Rejected by test validator.",
                ),
            ),
            validated_at=NOW,
        )


def build_compiler(
    calls: list[str],
    *,
    aggregate_output: tuple[Aggregate, ...] | None = None,
    tamper_confidence: bool = False,
    rejecting: bool = False,
) -> ProfileCompiler:
    """Construct the production compiler with observable test collaborators."""

    feature_registry = registry()
    validator = (
        _RejectingValidator()
        if rejecting
        else StructuralReleaseValidator(registry=feature_registry, version=semver())
    )
    return ProfileCompiler(
        registry=feature_registry,
        aggregator=_Aggregator(
            calls, (aggregate(),) if aggregate_output is None else aggregate_output
        ),
        partial_pooler=_Pooler(calls),
        residual_computer=_ResidualComputer(calls),
        conditional_residual_estimator=_ConditionalEstimator(calls),
        interaction_estimator=_InteractionEstimator(calls),
        drift_estimator=_DriftEstimator(calls),
        confidence_estimator=_ConfidenceEstimator(calls, tamper=tamper_confidence),
        validator=validator,
        compiler_version=semver(),
    )


def test_profile_compiler_orchestrates_ports_and_returns_valid_release() -> None:
    calls: list[str] = []
    compiler = build_compiler(calls)

    result = compiler.compile(compilation_request())

    assert calls == [
        "aggregate",
        "pool",
        "residual",
        "conditional",
        "interaction",
        "drift",
        "confidence",
    ]
    assert result.release.id == RELEASE_ID
    assert tuple(item.observation_id for item in result.release.observation_references) == (
        OBSERVATION_ID,
    )
    assert result.validation_report.is_valid()


def test_profile_compiler_rejects_missing_mandatory_stage_output() -> None:
    with pytest.raises(ProfileCompilationError, match="no mandatory components") as caught:
        build_compiler([], aggregate_output=()).compile(compilation_request())

    assert caught.value.details["stage"] == "aggregation"


def test_profile_compiler_rejects_confidence_stage_content_changes() -> None:
    with pytest.raises(ProfileCompilationError, match="non-confidence content"):
        build_compiler([], tamper_confidence=True).compile(compilation_request())


def test_profile_compiler_translates_invalid_stage_payloads_to_domain_error() -> None:
    wrong_owner = aggregate().model_copy(update={"tenant_id": UUID(int=990)})

    with pytest.raises(ProfileCompilationError, match="invalid release payload") as caught:
        build_compiler([], aggregate_output=(wrong_owner,)).compile(compilation_request())

    assert caught.value.details["error_count"] == 1


def test_profile_compiler_rejects_structurally_invalid_release() -> None:
    with pytest.raises(HVMValidationError, match="failed structural validation") as caught:
        build_compiler([], rejecting=True).compile(compilation_request())

    assert caught.value.details["release_id"] == str(RELEASE_ID)
