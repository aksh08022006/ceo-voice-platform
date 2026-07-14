"""Concrete, scientifically conservative compilation stages for Tier 1 scalar observations."""

from collections import defaultdict
from uuid import NAMESPACE_URL, UUID, uuid5

from ceo_voice.core.exceptions import ProfileCompilationError
from ceo_voice.models.base import UtcDatetime
from ceo_voice.profiles.contracts import ScalarBaselineSnapshot
from ceo_voice.voice import (
    Aggregate,
    AggregationRequest,
    ConditionalResidual,
    ConditionalResidualEstimationRequest,
    ConfidenceEstimationRequest,
    ConfidenceVector,
    DecisionState,
    DriftEstimationRequest,
    DriftState,
    FeatureReference,
    FeatureRegistryReader,
    Interaction,
    InteractionEstimationRequest,
    Observation,
    ObservationState,
    PartialPoolingRequest,
    ProfileComponents,
    Residual,
    ResidualComputationRequest,
    ScalarValue,
    VoiceContext,
)


def _component_id(build_id: UUID, kind: str, *parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, ":".join((str(build_id), kind, *(str(item) for item in parts))))


def _placeholder_confidence(evidence_count: int) -> ConfidenceVector:
    """Return structurally complete, deliberately non-authoritative confidence."""

    return ConfidenceVector(
        measurement_reliability=0,
        attribution_reliability=0,
        coverage=0,
        effective_support=0,
        context_diversity=0,
        stability=0,
        cross_context_robustness=0,
        nuisance_robustness=0,
        distinctiveness=0,
        freshness=0,
        calibration=0,
        conflict=0,
        evidence_count=evidence_count,
        independent_cluster_count=0,
        variance=0,
    )


class DescriptiveScalarAggregator:
    """Create language-core arithmetic means from exact scalar observations.

    This is a descriptive corpus summary, not a claim of distinctiveness or a statistical model.
    Missing and abstained observations remain release-pinned but do not become numeric zeroes.
    """

    def __init__(self, *, registry: FeatureRegistryReader, created_at: UtcDatetime) -> None:
        self._registry = registry
        self._created_at = created_at

    def aggregate(self, request: AggregationRequest) -> tuple[Aggregate, ...]:
        groups: dict[tuple[FeatureReference, str], list[Observation]] = defaultdict(list)
        for observation in request.observations:
            if observation.state is ObservationState.OBSERVED:
                groups[(observation.feature, observation.context.language)].append(observation)

        aggregates: list[Aggregate] = []
        for (feature, language), observations in groups.items():
            scalar_values = tuple(item.value for item in observations)
            if not scalar_values or any(
                not isinstance(item, ScalarValue) for item in scalar_values
            ):
                raise ProfileCompilationError(
                    "descriptive compiler supports scalar observations only",
                    details={"feature_id": feature.feature_id},
                )
            typed_values = tuple(item for item in scalar_values if isinstance(item, ScalarValue))
            units = {item.unit for item in typed_values}
            if len(units) != 1:
                raise ProfileCompilationError(
                    "scalar observation units are inconsistent",
                    details={"feature_id": feature.feature_id},
                )
            evidence_ids = tuple(
                sorted(
                    {
                        reference.evidence_unit_id
                        for observation in observations
                        for reference in observation.evidence
                    },
                    key=lambda item: item.int,
                )
            )
            definition = self._registry.get(feature)
            aggregates.append(
                Aggregate(
                    id=_component_id(request.build_id, "aggregate", feature.feature_id, language),
                    tenant_id=observations[0].tenant_id,
                    voice_identity_id=observations[0].voice_identity_id,
                    feature=feature,
                    context=VoiceContext(language=language),
                    value=ScalarValue(
                        value=sum(item.value for item in typed_values) / len(typed_values),
                        unit=typed_values[0].unit,
                    ),
                    observation_ids=tuple(
                        sorted((item.id for item in observations), key=lambda item: item.int)
                    ),
                    evidence_unit_ids=evidence_ids,
                    aggregation_strategy=definition.aggregation_strategy,
                    confidence=_placeholder_confidence(len(evidence_ids)),
                    decision_state=DecisionState.DESCRIPTIVE,
                    created_at=self._created_at,
                )
            )
        return tuple(sorted(aggregates, key=lambda item: item.id.int))


class DescriptivePartialPooler:
    """Preserve descriptive aggregates until an empirical pooling model is supplied."""

    def pool(self, request: PartialPoolingRequest) -> tuple[Aggregate, ...]:
        return request.aggregates


class ScalarBaselineResidualComputer:
    """Subtract explicit, versioned scalar baselines without inventing cohort statistics."""

    def __init__(self, *, baselines: ScalarBaselineSnapshot, created_at: UtcDatetime) -> None:
        self._baselines = baselines
        self._created_at = created_at

    def compute(self, request: ResidualComputationRequest) -> tuple[Residual, ...]:
        residuals: list[Residual] = []
        for aggregate in request.pooled_aggregates:
            if not isinstance(aggregate.value, ScalarValue):
                raise ProfileCompilationError("scalar residual computer received a non-scalar")
            try:
                baseline = self._baselines.get(aggregate.feature)
            except KeyError as exc:
                raise ProfileCompilationError(
                    "feature has no explicit scalar baseline",
                    details={"feature_id": aggregate.feature.feature_id},
                ) from exc
            if baseline.value.unit != aggregate.value.unit:
                raise ProfileCompilationError(
                    "aggregate and baseline units differ",
                    details={"feature_id": aggregate.feature.feature_id},
                )
            residuals.append(
                Residual(
                    id=_component_id(
                        request.build_id,
                        "residual",
                        aggregate.feature.feature_id,
                        aggregate.context.language,
                    ),
                    tenant_id=aggregate.tenant_id,
                    voice_identity_id=request.voice_identity_id,
                    feature=aggregate.feature,
                    aggregate_id=aggregate.id,
                    baseline=baseline.reference,
                    context=aggregate.context,
                    value=ScalarValue(
                        value=aggregate.value.value - baseline.value.value,
                        unit=aggregate.value.unit,
                    ),
                    evidence_unit_ids=aggregate.evidence_unit_ids,
                    confidence=aggregate.confidence,
                    decision_state=DecisionState.DESCRIPTIVE,
                    created_at=self._created_at,
                )
            )
        return tuple(sorted(residuals, key=lambda item: item.id.int))


class DescriptivePlatformResidualEstimator:
    """Represent observed platform means as deltas from the corpus-wide feature mean."""

    def __init__(self, *, created_at: UtcDatetime) -> None:
        self._created_at = created_at

    def estimate(
        self, request: ConditionalResidualEstimationRequest
    ) -> tuple[ConditionalResidual, ...]:
        observed = tuple(
            item
            for item in request.observations
            if item.state is ObservationState.OBSERVED and isinstance(item.value, ScalarValue)
        )
        core = {(item.feature, item.context.language): item for item in request.core_residuals}
        groups: dict[tuple[FeatureReference, str, object, object], list[Observation]] = defaultdict(
            list
        )
        for observation in observed:
            if observation.context.platform is not None:
                groups[
                    (
                        observation.feature,
                        observation.context.language,
                        observation.context.platform,
                        observation.context.content_form,
                    )
                ].append(observation)
        all_values: dict[tuple[FeatureReference, str], list[float]] = defaultdict(list)
        for observation in observed:
            assert isinstance(observation.value, ScalarValue)
            all_values[(observation.feature, observation.context.language)].append(
                observation.value.value
            )

        conditionals: list[ConditionalResidual] = []
        for (feature, language, platform, content_form), observations in groups.items():
            parent = core[(feature, language)]
            values = tuple(item.value for item in observations)
            scalar_values = tuple(item for item in values if isinstance(item, ScalarValue))
            units = {item.unit for item in scalar_values}
            if len(units) != 1:
                raise ProfileCompilationError("platform observation units are inconsistent")
            global_mean = sum(all_values[(feature, language)]) / len(
                all_values[(feature, language)]
            )
            platform_mean = sum(item.value for item in scalar_values) / len(scalar_values)
            evidence_ids = tuple(
                sorted(
                    {
                        reference.evidence_unit_id
                        for observation in observations
                        for reference in observation.evidence
                    },
                    key=lambda item: item.int,
                )
            )
            conditionals.append(
                ConditionalResidual(
                    id=_component_id(
                        request.build_id,
                        "conditional",
                        feature.feature_id,
                        language,
                        platform,
                        content_form,
                    ),
                    tenant_id=parent.tenant_id,
                    voice_identity_id=parent.voice_identity_id,
                    feature=feature,
                    parent_residual_id=parent.id,
                    condition=VoiceContext(
                        language=language,
                        platform=platform,
                        content_form=content_form,
                    ),
                    delta=ScalarValue(
                        value=platform_mean - global_mean,
                        unit=scalar_values[0].unit,
                    ),
                    transfer_confidence=0,
                    evidence_unit_ids=evidence_ids,
                    confidence=_placeholder_confidence(len(evidence_ids)),
                    decision_state=DecisionState.DESCRIPTIVE,
                    created_at=self._created_at,
                )
            )
        return tuple(sorted(conditionals, key=lambda item: item.id.int))


class EmptyInteractionEstimator:
    """Return no interactions until a validated interaction estimator exists."""

    def estimate(self, request: InteractionEstimationRequest) -> tuple[Interaction, ...]:
        del request
        return ()


class EmptyDriftEstimator:
    """Return no drift assertion; incremental rebuilds still preserve release lineage."""

    def estimate(self, request: DriftEstimationRequest) -> tuple[DriftState, ...]:
        del request
        return ()


class EvidenceDerivedConfidenceEstimator:
    """Populate transparent coverage confidence while withholding unmeasured dimensions."""

    def estimate(self, request: ConfidenceEstimationRequest) -> ProfileComponents:
        observations = {item.id: item for item in request.observations}
        feature_totals: dict[FeatureReference, int] = defaultdict(int)
        for observation in request.observations:
            feature_totals[observation.feature] += 1

        aggregates = tuple(
            aggregate.model_copy(
                update={
                    "confidence": self._aggregate_confidence(
                        aggregate, observations, feature_totals[aggregate.feature]
                    )
                }
            )
            for aggregate in request.components.aggregates
        )
        confidence_by_aggregate = {item.id: item.confidence for item in aggregates}
        residuals = tuple(
            residual.model_copy(
                update={"confidence": confidence_by_aggregate[residual.aggregate_id]}
            )
            for residual in request.components.residuals
        )
        conditionals = tuple(
            item.model_copy(
                update={
                    "confidence": self._conditional_confidence(
                        item.feature,
                        item.evidence_unit_ids,
                        tuple(observations.values()),
                    )
                }
            )
            for item in request.components.conditional_residuals
        )
        return ProfileComponents(
            aggregates=aggregates,
            residuals=residuals,
            conditional_residuals=conditionals,
            interactions=request.components.interactions,
            drift_states=request.components.drift_states,
        )

    def _aggregate_confidence(
        self,
        aggregate: Aggregate,
        observations: dict[UUID, Observation],
        total_opportunities: int,
    ) -> ConfidenceVector:
        contributing = tuple(observations[item] for item in aggregate.observation_ids)
        measurement = sum(item.quality for item in contributing) / len(contributing)
        evidence_references = tuple(
            reference for item in contributing for reference in item.evidence
        )
        attribution = sum(
            item.weight_components.target_attribution for item in evidence_references
        ) / len(evidence_references)
        independent_clusters = len({item.independence_cluster_id for item in evidence_references})
        coverage = len(contributing) / total_opportunities if total_opportunities else 0
        return self._evidence_confidence(
            evidence_count=len(aggregate.evidence_unit_ids),
            independent_cluster_count=independent_clusters,
            coverage=coverage,
            measurement_reliability=measurement,
            attribution_reliability=attribution,
        )

    def _conditional_confidence(
        self,
        feature: FeatureReference,
        evidence_unit_ids: tuple[UUID, ...],
        observations: tuple[Observation, ...],
    ) -> ConfidenceVector:
        selected_ids = set(evidence_unit_ids)
        contributing = tuple(
            observation
            for observation in observations
            if observation.feature == feature
            and any(item.evidence_unit_id in selected_ids for item in observation.evidence)
        )
        references = tuple(
            item
            for observation in contributing
            for item in observation.evidence
            if item.evidence_unit_id in selected_ids
        )
        measurement = (
            sum(item.quality for item in contributing) / len(contributing) if contributing else 0
        )
        attribution = (
            sum(item.weight_components.target_attribution for item in references) / len(references)
            if references
            else 0
        )
        return self._evidence_confidence(
            evidence_count=len(evidence_unit_ids),
            independent_cluster_count=len({item.independence_cluster_id for item in references}),
            coverage=0,
            measurement_reliability=measurement,
            attribution_reliability=attribution,
        )

    @staticmethod
    def _evidence_confidence(
        *,
        evidence_count: int,
        independent_cluster_count: int,
        coverage: float,
        measurement_reliability: float,
        attribution_reliability: float,
    ) -> ConfidenceVector:
        return ConfidenceVector(
            measurement_reliability=measurement_reliability,
            attribution_reliability=attribution_reliability,
            coverage=coverage,
            effective_support=float(independent_cluster_count),
            context_diversity=0,
            stability=0,
            cross_context_robustness=0,
            nuisance_robustness=0,
            distinctiveness=0,
            freshness=0,
            calibration=0,
            conflict=0,
            evidence_count=evidence_count,
            independent_cluster_count=independent_cluster_count,
            variance=0,
        )
