"""Typed, immutable value representations used by HVM observations and components."""

from itertools import pairwise
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, FiniteFloat, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr
from ceo_voice.voice.enums import FeatureValueType, VectorNormalization
from ceo_voice.voice.primitives import NonNegativeFloat, SemanticVersion, UnitInterval

_PROBABILITY_TOLERANCE = 1e-9


class ScalarValue(ContractModel):
    """One finite numeric value with explicit measurement unit."""

    kind: Literal[FeatureValueType.SCALAR] = FeatureValueType.SCALAR
    value: FiniteFloat = Field(description="Finite observed or estimated value.")
    unit: NonEmptyStr = Field(description="Measurement unit or normalized scale.")


class QuantilePoint(ContractModel):
    """One point in an empirical or estimated continuous distribution."""

    probability: UnitInterval = Field(description="Cumulative probability.")
    value: FiniteFloat = Field(description="Value at the cumulative probability.")


class ContinuousDistributionValue(ContractModel):
    """Robust continuous distribution summary with uncertainty-support metadata."""

    kind: Literal[FeatureValueType.CONTINUOUS_DISTRIBUTION] = (
        FeatureValueType.CONTINUOUS_DISTRIBUTION
    )
    unit: NonEmptyStr = Field(description="Measurement unit.")
    quantiles: tuple[QuantilePoint, ...] = Field(
        min_length=1, description="Strictly ordered distribution quantiles."
    )
    mean: FiniteFloat | None = Field(default=None, description="Optional arithmetic mean.")
    variance: NonNegativeFloat = Field(description="Estimated distribution variance.")
    sample_count: int = Field(ge=1, description="Raw supporting observation count.")
    effective_sample_size: NonNegativeFloat = Field(
        description="Support after dependence and weighting adjustments."
    )

    @model_validator(mode="after")
    def validate_distribution(self) -> Self:
        """Require increasing probabilities, nondecreasing values, and bounded support."""

        probabilities = tuple(point.probability for point in self.quantiles)
        values = tuple(point.value for point in self.quantiles)
        if any(left >= right for left, right in pairwise(probabilities)):
            raise ValueError("quantile probabilities must be strictly increasing")
        if any(left > right for left, right in pairwise(values)):
            raise ValueError("quantile values must be nondecreasing")
        if self.effective_sample_size > self.sample_count:
            raise ValueError("effective sample size must not exceed raw sample count")
        return self


class CategoryProbability(ContractModel):
    """Probability assigned to one controlled categorical value."""

    category: NonEmptyStr = Field(description="Controlled-vocabulary category identifier.")
    probability: UnitInterval = Field(description="Calibrated category probability.")


class CategoricalDistributionValue(ContractModel):
    """Calibrated categorical distribution over a versioned vocabulary."""

    kind: Literal[FeatureValueType.CATEGORICAL_DISTRIBUTION] = (
        FeatureValueType.CATEGORICAL_DISTRIBUTION
    )
    vocabulary_id: NonEmptyStr = Field(description="Stable controlled-vocabulary identifier.")
    vocabulary_version: SemanticVersion = Field(description="Exact vocabulary version.")
    probabilities: tuple[CategoryProbability, ...] = Field(
        min_length=1, description="Probabilities for known categories."
    )
    unknown_probability: UnitInterval = Field(
        description="Probability assigned to unknown or other categories."
    )

    @model_validator(mode="after")
    def validate_probabilities(self) -> Self:
        """Reject duplicate categories and non-normalized distributions."""

        categories = tuple(item.category for item in self.probabilities)
        if len(categories) != len(set(categories)):
            raise ValueError("categorical distribution categories must be unique")
        total = sum(item.probability for item in self.probabilities) + self.unknown_probability
        if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError("categorical probabilities must sum to one")
        return self


class CountDistributionValue(ContractModel):
    """Count distribution summary tied to an explicit opportunity exposure."""

    kind: Literal[FeatureValueType.COUNT_DISTRIBUTION] = FeatureValueType.COUNT_DISTRIBUTION
    unit: NonEmptyStr = Field(description="Counted phenomenon unit.")
    exposure: NonNegativeFloat = Field(description="Opportunity or exposure denominator.")
    mean: NonNegativeFloat = Field(description="Estimated mean count per exposure unit.")
    variance: NonNegativeFloat = Field(description="Estimated count variance.")
    zero_probability: UnitInterval = Field(description="Observed or estimated zero probability.")
    sample_count: int = Field(ge=1, description="Raw supporting observation count.")


class TransitionProbability(ContractModel):
    """Directed transition between two states in a sequence model."""

    source: NonEmptyStr = Field(description="Source state identifier.")
    target: NonEmptyStr = Field(description="Target state identifier.")
    probability: UnitInterval = Field(description="Conditional transition probability.")
    support_count: int = Field(ge=1, description="Observed transition support.")


class SequenceModelValue(ContractModel):
    """Finite state vocabulary and explicitly supported directed transitions."""

    kind: Literal[FeatureValueType.SEQUENCE_MODEL] = FeatureValueType.SEQUENCE_MODEL
    vocabulary_id: NonEmptyStr = Field(description="Stable state-vocabulary identifier.")
    vocabulary_version: SemanticVersion = Field(description="Exact state-vocabulary version.")
    states: tuple[NonEmptyStr, ...] = Field(min_length=1, description="Allowed states.")
    start_state: NonEmptyStr = Field(description="Explicit sequence start state.")
    end_state: NonEmptyStr = Field(description="Explicit sequence end state.")
    transitions: tuple[TransitionProbability, ...] = Field(
        default_factory=tuple, description="Supported transition probabilities."
    )

    @model_validator(mode="after")
    def validate_states(self) -> Self:
        """Require unique states and transition endpoints in the declared vocabulary."""

        if len(self.states) != len(set(self.states)):
            raise ValueError("sequence states must be unique")
        if self.start_state not in self.states or self.end_state not in self.states:
            raise ValueError("sequence start and end states must be declared")
        edges = tuple((item.source, item.target) for item in self.transitions)
        if len(edges) != len(set(edges)):
            raise ValueError("sequence transitions must be unique")
        if any(source not in self.states or target not in self.states for source, target in edges):
            raise ValueError("sequence transitions must reference declared states")
        return self


class SparseVectorEntry(ContractModel):
    """One non-zero value in a versioned sparse dimension registry."""

    dimension: NonEmptyStr = Field(description="Stable dimension identifier.")
    value: FiniteFloat = Field(description="Finite dimension value.")


class SparseVectorValue(ContractModel):
    """Sparse vector whose dimensions and normalization semantics are explicit."""

    kind: Literal[FeatureValueType.SPARSE_VECTOR] = FeatureValueType.SPARSE_VECTOR
    dimension_registry_id: NonEmptyStr = Field(description="Dimension-registry identifier.")
    dimension_registry_version: SemanticVersion = Field(description="Exact registry version.")
    normalization: VectorNormalization = Field(description="Applied normalization semantics.")
    entries: tuple[SparseVectorEntry, ...] = Field(
        default_factory=tuple, description="Non-zero vector entries."
    )

    @model_validator(mode="after")
    def validate_entries(self) -> Self:
        """Reject duplicate or explicitly zero sparse dimensions."""

        dimensions = tuple(item.dimension for item in self.entries)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("sparse-vector dimensions must be unique")
        if any(item.value == 0 for item in self.entries):
            raise ValueError("sparse vectors must omit zero-valued dimensions")
        return self


class GraphNode(ContractModel):
    """Named node in a typed graph value."""

    node_id: NonEmptyStr = Field(description="Stable node identifier within the graph.")
    node_type: NonEmptyStr = Field(description="Controlled node type.")


class GraphEdge(ContractModel):
    """Directed, weighted relationship in a graph value."""

    source: NonEmptyStr = Field(description="Source node identifier.")
    target: NonEmptyStr = Field(description="Target node identifier.")
    relation: NonEmptyStr = Field(description="Controlled relationship type.")
    weight: FiniteFloat = Field(description="Finite relationship parameter.")
    support_count: int = Field(ge=1, description="Independent support count.")


class GraphValue(ContractModel):
    """Versioned graph with explicit node and edge semantics."""

    kind: Literal[FeatureValueType.GRAPH] = FeatureValueType.GRAPH
    schema_id: NonEmptyStr = Field(description="Graph-schema identifier.")
    schema_version: SemanticVersion = Field(description="Exact graph-schema version.")
    nodes: tuple[GraphNode, ...] = Field(min_length=1, description="Graph nodes.")
    edges: tuple[GraphEdge, ...] = Field(default_factory=tuple, description="Graph edges.")

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        """Require unique nodes and edges that resolve within the graph."""

        node_ids = tuple(node.node_id for node in self.nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph nodes must be unique")
        edge_keys = tuple((edge.source, edge.target, edge.relation) for edge in self.edges)
        if len(edge_keys) != len(set(edge_keys)):
            raise ValueError("graph edges must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("graph edges must reference declared nodes")
        return self


class IntervalValue(ContractModel):
    """Bounded numeric preference or constraint with explicit inclusivity."""

    kind: Literal[FeatureValueType.INTERVAL] = FeatureValueType.INTERVAL
    lower: FiniteFloat | None = Field(default=None, description="Optional lower bound.")
    upper: FiniteFloat | None = Field(default=None, description="Optional upper bound.")
    lower_inclusive: bool = Field(description="Whether the lower bound is inclusive.")
    upper_inclusive: bool = Field(description="Whether the upper bound is inclusive.")
    unit: NonEmptyStr = Field(description="Measurement unit.")

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Require at least one bound and reject reversed or empty intervals."""

        if self.lower is None and self.upper is None:
            raise ValueError("an interval requires at least one bound")
        if self.lower is not None and self.upper is not None:
            if self.lower > self.upper:
                raise ValueError("interval lower bound must not exceed upper bound")
            if self.lower == self.upper and not (self.lower_inclusive and self.upper_inclusive):
                raise ValueError("equal interval bounds must both be inclusive")
        return self


type MixtureComponentValue = Annotated[
    ScalarValue | ContinuousDistributionValue | CategoricalDistributionValue,
    Field(discriminator="kind"),
]


class MixtureComponent(ContractModel):
    """One interpretable component and posterior weight in a mixture."""

    label: NonEmptyStr = Field(description="Human-reviewable component label.")
    weight: UnitInterval = Field(description="Posterior mixture weight.")
    value: MixtureComponentValue = Field(description="Typed component distribution or center.")


class MixtureValue(ContractModel):
    """Finite interpretable mixture used when a single average would erase real modes."""

    kind: Literal[FeatureValueType.MIXTURE] = FeatureValueType.MIXTURE
    components: tuple[MixtureComponent, ...] = Field(
        min_length=2, description="Distinct mixture components."
    )

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        """Require unique labels and normalized mixture weights."""

        labels = tuple(component.label for component in self.components)
        if len(labels) != len(set(labels)):
            raise ValueError("mixture component labels must be unique")
        total = sum(component.weight for component in self.components)
        if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError("mixture weights must sum to one")
        return self


class WeightedPrototypeReference(ContractModel):
    """Reference and retrieval weight for one approved prototype."""

    prototype_id: UUID = Field(description="Prototype domain-object identifier.")
    weight: UnitInterval = Field(description="Relative representativeness weight.")


class PrototypeSetValue(ContractModel):
    """Diverse, governed prototype-set reference rather than copied example text."""

    kind: Literal[FeatureValueType.PROTOTYPE_SET] = FeatureValueType.PROTOTYPE_SET
    prototypes: tuple[WeightedPrototypeReference, ...] = Field(
        min_length=1, description="Approved prototype references."
    )

    @model_validator(mode="after")
    def validate_prototypes(self) -> Self:
        """Reject duplicate prototype references."""

        identifiers = tuple(item.prototype_id for item in self.prototypes)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("prototype-set references must be unique")
        return self


type VoiceValue = Annotated[
    ScalarValue
    | ContinuousDistributionValue
    | CategoricalDistributionValue
    | CountDistributionValue
    | SequenceModelValue
    | SparseVectorValue
    | GraphValue
    | IntervalValue
    | MixtureValue
    | PrototypeSetValue,
    Field(discriminator="kind"),
]
