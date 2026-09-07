"""Compact voice selection should not lose rhythm to alphabetic ties."""

from uuid import UUID

import pytest

from ceo_voice.context.voice import VoiceCompiler
from ceo_voice.models.enums import Platform
from ceo_voice.voice import FeatureRegistry, ProfileComponents
from tests.unit.voice.factories import (
    LEADER_ID,
    NOW,
    REGISTRY_ID,
    feature_definition,
    release,
    residual,
    semver,
)


@pytest.mark.parametrize("weaker_rhythm", [False, True])
def test_rhythm_wins_a_confidence_tie_but_never_overrides_confidence(weaker_rhythm: bool) -> None:
    count = feature_definition().model_copy(update={"feature_id": "analysis.character-count"})
    rhythm = feature_definition().model_copy(
        update={"feature_id": "analysis.sentence-median-words"}
    )
    registry = FeatureRegistry.build(
        registry_id=REGISTRY_ID, version=semver(), definitions=(count, rhythm), created_at=NOW
    )
    count_residual = residual(definition=count)
    rhythm_residual = residual(definition=rhythm).model_copy(update={"id": UUID(int=902)})
    if weaker_rhythm:
        rhythm_residual = rhythm_residual.model_copy(
            update={
                "confidence": rhythm_residual.confidence.model_copy(
                    update={"measurement_reliability": 0.8}
                )
            }
        )
    source = release().model_copy(
        update={
            "registry": registry.reference,
            "components": ProfileComponents(residuals=(count_residual, rhythm_residual)),
        }
    )
    result = VoiceCompiler(registry=registry, maximum_features=1).compile(
        source,
        leader_id=LEADER_ID,
        platform=Platform.LINKEDIN,
        language="en",
        audience="executives",
        compiled_at=NOW,
    )
    assert result.target.features[0].feature_id == (
        count.feature_id if weaker_rhythm else rhythm.feature_id
    )
