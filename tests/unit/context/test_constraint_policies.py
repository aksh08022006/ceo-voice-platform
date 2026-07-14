"""Constraint-source compilation and hard-conflict semantics."""

from typing import cast
from uuid import UUID

import pytest

from ceo_voice.context import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
    ContextCompilationError,
    UserConstraint,
    create_context_compiler,
)
from ceo_voice.voice import (
    ConstraintBasis,
    ConstraintSeverity,
    NegativeConstraint,
    ScalarValue,
    TimeRange,
)
from tests.unit.context.factories import active_voice_release, compilation_input
from tests.unit.voice.factories import (
    ACTOR_ID,
    IDENTITY_ID,
    NOW,
    TENANT_ID,
    context,
    evidence_reference,
    release,
    validation_report,
)


def _user(
    number: int,
    *,
    operator: ConstraintOperator,
    value: object,
    key: str = "format.rule",
) -> UserConstraint:
    return UserConstraint(
        constraint_id=f"user.rule.{number}",
        category=ConstraintCategory.FORMATTING,
        strength=ConstraintStrength.HARD,
        operator=operator,
        key=key,
        value=value,
        priority=80,
        rationale="test conflict policy",
    )


def test_constraint_compiler_rejects_ambiguous_or_impossible_hard_rules() -> None:
    cases = (
        (
            (_user(1, operator=ConstraintOperator.EQUALS, value="a"),) * 2,
            None,
        ),
        (
            (
                _user(1, operator=ConstraintOperator.EQUALS, value="a"),
                _user(2, operator=ConstraintOperator.EQUALS, value="b"),
            ),
            "format.rule:multiple_equals",
        ),
        (
            (
                _user(1, operator=ConstraintOperator.EQUALS, value="a"),
                _user(2, operator=ConstraintOperator.PROHIBIT, value="a"),
            ),
            "format.rule:equals_prohibited",
        ),
        (
            (_user(1, operator=ConstraintOperator.MAXIMUM, value="many"),),
            "unsupported_request",
        ),
        (
            (
                _user(1, operator=ConstraintOperator.EQUALS, value=5),
                _user(2, operator=ConstraintOperator.MINIMUM, value=6),
            ),
            "format.rule:equals_below_minimum",
        ),
        (
            (
                _user(1, operator=ConstraintOperator.EQUALS, value=7),
                _user(2, operator=ConstraintOperator.MAXIMUM, value=6),
            ),
            "format.rule:equals_above_maximum",
        ),
    )

    for constraints, expected in cases:
        with pytest.raises(ContextCompilationError) as caught:
            create_context_compiler().compile(compilation_input(user_constraints=constraints))
        if expected == "unsupported_request":
            assert caught.value.details["reason"] == expected
        elif expected is None:
            assert caught.value.details["reason"] == "constraint_conflict"
        else:
            assert expected in cast(tuple[str, ...], caught.value.details["conflicts"])


def test_hvm_negative_constraints_preserve_strength_value_frequency_and_evidence() -> None:
    base = release()
    negative = NegativeConstraint(
        id=UUID(int=951),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=base.components.residuals[0].feature,
        basis=ConstraintBasis.EXPLICIT_POLICY,
        severity=ConstraintSeverity.HARD,
        scope=context(),
        prohibited_value=ScalarValue(value=1, unit="occurrence"),
        frequency_ceiling=0.1,
        authority="target_leader",
        actor_id=ACTOR_ID,
        evidence=(),
        effective_range=TimeRange(starts_at=NOW),
    )
    updated = base.model_copy(update={"negative_constraints": (negative,)})
    managed = active_voice_release(
        release_value=updated,
        report=validation_report(release_value=updated),
    )

    context_result = create_context_compiler().compile(compilation_input(voice=managed))
    negative_rules = tuple(
        item
        for item in context_result.constraints.constraints
        if item.category is ConstraintCategory.NEGATIVE_VOICE
    )

    assert len(negative_rules) == 2
    assert all(item.strength is ConstraintStrength.HARD for item in negative_rules)
    assert {item.operator for item in negative_rules} == {
        ConstraintOperator.PROHIBIT,
        ConstraintOperator.MAXIMUM,
    }
    assert all(negative.id in item.trace_ids for item in negative_rules)

    statistical = negative.model_copy(
        update={
            "id": UUID(int=952),
            "basis": ConstraintBasis.STATISTICAL_AVOIDANCE,
            "severity": ConstraintSeverity.SOFT,
            "authority": None,
            "actor_id": None,
            "evidence": (evidence_reference(),),
        }
    )
    statistical_release = base.model_copy(update={"negative_constraints": (statistical,)})
    statistical_managed = active_voice_release(
        release_value=statistical_release,
        report=validation_report(release_value=statistical_release),
    )
    statistical_result = create_context_compiler().compile(
        compilation_input(voice=statistical_managed)
    )
    statistical_rules = tuple(
        item
        for item in statistical_result.constraints.constraints
        if item.category is ConstraintCategory.NEGATIVE_VOICE
    )
    assert all(item.strength is ConstraintStrength.SOFT for item in statistical_rules)
    assert all(len(item.trace_ids) == 2 for item in statistical_rules)
