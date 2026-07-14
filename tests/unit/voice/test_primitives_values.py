"""Behavior tests for HVM primitive and typed-value invariants."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.models.enums import Platform
from ceo_voice.voice import (
    CategoricalDistributionValue,
    CategoryProbability,
    ContinuousDistributionValue,
    CountDistributionValue,
    GraphEdge,
    GraphNode,
    GraphValue,
    IntervalValue,
    LanguageApplicability,
    MixtureComponent,
    MixtureValue,
    PlatformApplicability,
    PrototypeSetValue,
    QuantilePoint,
    ScalarValue,
    SemanticVersion,
    SequenceModelValue,
    SparseVectorEntry,
    SparseVectorValue,
    TimeRange,
    TransitionProbability,
    VectorNormalization,
    VoiceContext,
    WeightedPrototypeReference,
)
from tests.unit.voice.factories import NOW


def test_semantic_version_parses_renders_and_compares_precedence() -> None:
    prerelease = SemanticVersion.parse("1.2.3-alpha.2+build.7")
    later_prerelease = SemanticVersion.parse("1.2.3-alpha.10")
    stable = SemanticVersion.parse("1.2.3")

    assert str(prerelease) == "1.2.3-alpha.2+build.7"
    assert prerelease.compare_precedence(later_prerelease) < 0
    assert later_prerelease.compare_precedence(stable) < 0
    assert stable.compare_precedence(SemanticVersion.parse("1.2.3+other")) == 0
    assert SemanticVersion.parse("2.0.0").compare_precedence(stable) > 0
    assert SemanticVersion.parse("1.3.0").compare_precedence(stable) > 0
    assert SemanticVersion.parse("1.2.4").compare_precedence(stable) > 0


@pytest.mark.parametrize(
    "value",
    ("1", "1.0", "01.0.0", "1.0.0-01", "1.0.0-alpha_1", "1.0.0+bad!"),
)
def test_semantic_version_rejects_invalid_strings(value: str) -> None:
    with pytest.raises(ValueError, match=r"invalid semantic version|leading zeroes"):
        SemanticVersion.parse(value)


def test_semantic_version_is_immutable_and_serialization_safe() -> None:
    version = SemanticVersion.parse("1.2.3")

    with pytest.raises(ValidationError):
        version.__setattr__("major", 2)
    assert SemanticVersion.model_validate_json(version.model_dump_json()) == version


def test_applicability_requires_explicit_all_or_enumerated_scope() -> None:
    assert LanguageApplicability(all_languages=True, languages=()).all_languages
    assert PlatformApplicability(all_platforms=False, platforms=(Platform.LINKEDIN,)).platforms == (
        Platform.LINKEDIN,
    )

    with pytest.raises(ValidationError, match="must not enumerate"):
        LanguageApplicability(all_languages=True, languages=("en",))
    with pytest.raises(ValidationError, match="at least one language"):
        LanguageApplicability(all_languages=False, languages=())
    with pytest.raises(ValidationError, match="must be unique"):
        PlatformApplicability(all_platforms=False, platforms=(Platform.X, Platform.X))
    with pytest.raises(ValidationError, match="at least one platform"):
        PlatformApplicability(all_platforms=False, platforms=())


def test_time_range_normalizes_and_applies_closed_open_semantics() -> None:
    local = datetime(2026, 7, 14, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    time_range = TimeRange(starts_at=NOW, ends_at=NOW + timedelta(hours=1))

    assert time_range.contains(local)
    assert not time_range.contains(NOW + timedelta(hours=1))
    with pytest.raises(ValueError, match="timezone information"):
        time_range.contains(datetime(2026, 7, 14))
    with pytest.raises(ValidationError, match="later"):
        TimeRange(starts_at=NOW, ends_at=NOW)


def test_voice_context_exposes_conditioning_without_magic_scope_strings() -> None:
    assert not VoiceContext(language="en").is_conditioned()
    assert VoiceContext(language="en", platform=Platform.X).is_conditioned()


def test_scalar_and_continuous_values_round_trip() -> None:
    scalar = ScalarValue(value=0.4, unit="rate")
    distribution = ContinuousDistributionValue(
        unit="tokens",
        quantiles=(
            QuantilePoint(probability=0.25, value=5),
            QuantilePoint(probability=0.5, value=10),
            QuantilePoint(probability=0.9, value=20),
        ),
        mean=11,
        variance=8,
        sample_count=10,
        effective_sample_size=8,
    )

    assert ScalarValue.model_validate_json(scalar.model_dump_json()) == scalar
    assert distribution.quantiles[-1].value == 20


def test_continuous_distribution_rejects_invalid_order_and_support() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        ContinuousDistributionValue(
            unit="tokens",
            quantiles=(
                QuantilePoint(probability=0.5, value=1),
                QuantilePoint(probability=0.5, value=2),
            ),
            variance=1,
            sample_count=2,
            effective_sample_size=2,
        )
    with pytest.raises(ValidationError, match="nondecreasing"):
        ContinuousDistributionValue(
            unit="tokens",
            quantiles=(
                QuantilePoint(probability=0.2, value=10),
                QuantilePoint(probability=0.8, value=5),
            ),
            variance=1,
            sample_count=2,
            effective_sample_size=2,
        )
    with pytest.raises(ValidationError, match="must not exceed"):
        ContinuousDistributionValue(
            unit="tokens",
            quantiles=(QuantilePoint(probability=0.5, value=10),),
            variance=1,
            sample_count=2,
            effective_sample_size=3,
        )


def test_categorical_distribution_requires_unique_normalized_categories() -> None:
    value = CategoricalDistributionValue(
        vocabulary_id="opening-moves",
        vocabulary_version=SemanticVersion.parse("1.0.0"),
        probabilities=(CategoryProbability(category="claim", probability=0.8),),
        unknown_probability=0.2,
    )
    assert value.probabilities[0].category == "claim"

    with pytest.raises(ValidationError, match="must sum to one"):
        CategoricalDistributionValue(
            vocabulary_id="opening-moves",
            vocabulary_version=SemanticVersion.parse("1.0.0"),
            probabilities=(CategoryProbability(category="claim", probability=0.4),),
            unknown_probability=0.2,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        CategoricalDistributionValue(
            vocabulary_id="opening-moves",
            vocabulary_version=SemanticVersion.parse("1.0.0"),
            probabilities=(
                CategoryProbability(category="claim", probability=0.4),
                CategoryProbability(category="claim", probability=0.4),
            ),
            unknown_probability=0.2,
        )


def test_count_and_sequence_models_are_typed_and_reference_safe() -> None:
    count = CountDistributionValue(
        unit="paragraph",
        exposure=4,
        mean=1.5,
        variance=0.5,
        zero_probability=0.1,
        sample_count=8,
    )
    sequence = SequenceModelValue(
        vocabulary_id="moves",
        vocabulary_version=SemanticVersion.parse("1.0.0"),
        states=("start", "claim", "end"),
        start_state="start",
        end_state="end",
        transitions=(
            TransitionProbability(source="start", target="claim", probability=1, support_count=4),
        ),
    )

    assert count.exposure == 4
    assert sequence.transitions[0].target == "claim"
    with pytest.raises(ValidationError, match="must be declared"):
        SequenceModelValue(
            vocabulary_id="moves",
            vocabulary_version=SemanticVersion.parse("1.0.0"),
            states=("start", "end"),
            start_state="missing",
            end_state="end",
        )
    with pytest.raises(ValidationError, match="transitions must be unique"):
        SequenceModelValue(
            vocabulary_id="moves",
            vocabulary_version=SemanticVersion.parse("1.0.0"),
            states=("start", "end"),
            start_state="start",
            end_state="end",
            transitions=(
                TransitionProbability(source="start", target="end", probability=1, support_count=1),
                TransitionProbability(source="start", target="end", probability=1, support_count=1),
            ),
        )


def test_sparse_vector_and_graph_reject_ambiguous_references() -> None:
    vector = SparseVectorValue(
        dimension_registry_id="function-words",
        dimension_registry_version=SemanticVersion.parse("1.0.0"),
        normalization=VectorNormalization.L2,
        entries=(SparseVectorEntry(dimension="and", value=0.4),),
    )
    graph = GraphValue(
        schema_id="move-graph",
        schema_version=SemanticVersion.parse("1.0.0"),
        nodes=(GraphNode(node_id="claim", node_type="move"),),
    )

    assert vector.entries[0].dimension == "and"
    assert graph.nodes[0].node_id == "claim"
    with pytest.raises(ValidationError, match="omit zero"):
        SparseVectorValue(
            dimension_registry_id="words",
            dimension_registry_version=SemanticVersion.parse("1.0.0"),
            normalization=VectorNormalization.NONE,
            entries=(SparseVectorEntry(dimension="and", value=0),),
        )
    with pytest.raises(ValidationError, match="declared nodes"):
        GraphValue(
            schema_id="moves",
            schema_version=SemanticVersion.parse("1.0.0"),
            nodes=(GraphNode(node_id="claim", node_type="move"),),
            edges=(
                GraphEdge(
                    source="claim", target="missing", relation="follows", weight=1, support_count=1
                ),
            ),
        )


def test_interval_mixture_and_prototype_set_enforce_bounds_and_identity() -> None:
    interval = IntervalValue(
        lower=1,
        upper=3,
        lower_inclusive=True,
        upper_inclusive=False,
        unit="sentences",
    )
    mixture = MixtureValue(
        components=(
            MixtureComponent(label="terse", weight=0.4, value=ScalarValue(value=5, unit="tokens")),
            MixtureComponent(
                label="explanatory", weight=0.6, value=ScalarValue(value=20, unit="tokens")
            ),
        )
    )
    prototype_set = PrototypeSetValue(
        prototypes=(WeightedPrototypeReference(prototype_id=UUID(int=1), weight=1),)
    )

    assert interval.upper == 3
    assert mixture.components[1].label == "explanatory"
    assert prototype_set.prototypes[0].prototype_id == UUID(int=1)
    with pytest.raises(ValidationError, match="at least one bound"):
        IntervalValue(
            lower=None,
            upper=None,
            lower_inclusive=True,
            upper_inclusive=True,
            unit="rate",
        )
    with pytest.raises(ValidationError, match="must sum to one"):
        MixtureValue(
            components=(
                MixtureComponent(label="a", weight=0.2, value=ScalarValue(value=1, unit="x")),
                MixtureComponent(label="b", weight=0.2, value=ScalarValue(value=2, unit="x")),
            )
        )
    with pytest.raises(ValidationError, match="must be unique"):
        PrototypeSetValue(
            prototypes=(
                WeightedPrototypeReference(prototype_id=UUID(int=1), weight=1),
                WeightedPrototypeReference(prototype_id=UUID(int=1), weight=1),
            )
        )
