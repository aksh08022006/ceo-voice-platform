"""Focused selection-policy tests for voice and structural compilers."""

from uuid import UUID

import pytest

from ceo_voice.context import (
    ContextCompilationError,
    ContextCompilationPolicy,
    StructuralSelectionPolicy,
    VoiceResolutionSource,
    create_context_compiler,
)
from ceo_voice.voice import (
    ConditionalResidual,
    DecisionState,
    DownstreamPermission,
    ExplicitPreference,
    PreferenceAuthority,
    ProfileComponents,
    ScalarValue,
    TimeRange,
)
from tests.unit.context.factories import active_voice_release, compilation_input
from tests.unit.voice.factories import (
    ACTOR_ID,
    IDENTITY_ID,
    NOW,
    TENANT_ID,
    confidence,
    context,
    feature_definition,
    registry,
    release,
    validation_report,
)


def test_voice_compiler_applies_platform_conditional_inheritance() -> None:
    base = release()
    parent = base.components.residuals[0]
    conditional = ConditionalResidual(
        id=UUID(int=801),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=parent.feature,
        parent_residual_id=parent.id,
        condition=context(),
        delta=ScalarValue(value=0.05, unit="residual"),
        transfer_confidence=0.9,
        evidence_unit_ids=parent.evidence_unit_ids,
        confidence=confidence(),
        decision_state=DecisionState.ACTIONABLE_STRONG,
        created_at=NOW,
    )
    updated = base.model_copy(
        update={
            "components": ProfileComponents(
                aggregates=base.components.aggregates,
                residuals=base.components.residuals,
                conditional_residuals=(conditional,),
            )
        }
    )
    report = validation_report(release_value=updated)
    managed = active_voice_release(release_value=updated, report=report)

    result = create_context_compiler().compile(compilation_input(voice=managed))
    selected = result.voice.features[0]

    assert selected.resolution_source is VoiceResolutionSource.PLATFORM_CONDITIONAL
    assert isinstance(selected.target_value, dict)
    assert selected.target_value["kind"] == "scalar"
    assert selected.target_value["unit"] == "residual"
    assert selected.target_value["value"] == pytest.approx(0.15)
    assert selected.conditional_delta == {
        "kind": "scalar",
        "value": 0.05,
        "unit": "residual",
    }
    assert selected.component_ids == (parent.id, conditional.id)


def test_voice_compiler_rejects_registry_without_generation_permission() -> None:
    descriptive = feature_definition().model_copy(
        update={
            "downstream_permissions": tuple(
                permission
                for permission in DownstreamPermission
                if permission is not DownstreamPermission.GENERATE
            )
        }
    )
    descriptive_release = release(feature=descriptive)
    managed = active_voice_release(
        release_value=descriptive_release,
        report=validation_report(release_value=descriptive_release),
    )
    compilation = compilation_input(voice=managed).model_copy(
        update={"feature_registry": registry(definition=descriptive)}
    )

    with pytest.raises(ContextCompilationError) as caught:
        create_context_compiler().compile(compilation)

    assert caught.value.details["reason"] == "insufficient_voice_guidance"


def test_explicit_preference_overrides_statistical_target_by_priority() -> None:
    base = release()
    feature = base.components.residuals[0].feature
    lower_priority = ExplicitPreference(
        id=UUID(int=811),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=feature,
        target=ScalarValue(value=0.7, unit="residual"),
        scope=context(),
        authority=PreferenceAuthority.TARGET_LEADER,
        priority=80,
        tolerance=0.05,
        actor_id=ACTOR_ID,
        rationale_category="editorial_preference",
        effective_range=TimeRange(starts_at=NOW),
        created_at=NOW,
    )
    selected_preference = lower_priority.model_copy(
        update={
            "id": UUID(int=812),
            "target": ScalarValue(value=0.9, unit="residual"),
            "priority": 90,
        }
    )
    updated = base.model_copy(
        update={"explicit_preferences": (lower_priority, selected_preference)}
    )
    managed = active_voice_release(
        release_value=updated,
        report=validation_report(release_value=updated),
    )

    result = create_context_compiler().compile(compilation_input(voice=managed))
    selected = result.voice.features[0]

    assert selected.resolution_source is VoiceResolutionSource.EXPLICIT_PREFERENCE
    assert selected.target_value == {"kind": "scalar", "value": 0.9, "unit": "residual"}
    assert selected.component_ids[-1] == selected_preference.id
    assert any(item.knowledge_id == str(lower_priority.id) for item in result.report.ignored_voice)


def test_structural_support_policy_can_fail_closed() -> None:
    policy = ContextCompilationPolicy(
        structure=StructuralSelectionPolicy(
            minimum_documents=100,
            minimum_leaders=2,
            minimum_comparable_fraction=0.5,
        )
    )

    with pytest.raises(ContextCompilationError) as caught:
        create_context_compiler(policy=policy).compile(compilation_input())

    assert caught.value.details["reason"] == "insufficient_structural_guidance"
