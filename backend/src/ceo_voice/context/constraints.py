"""Deterministic compilation and conflict detection for generation constraints."""

from collections import Counter, defaultdict
from datetime import datetime
from typing import cast

from pydantic import JsonValue

from ceo_voice.context.contracts import (
    CompiledConstraint,
    ConstraintBundle,
    ConstraintSummary,
    PlatformContract,
    UserConstraint,
)
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
)
from ceo_voice.core.exceptions import ContextCompilationError
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.components import NegativeConstraint
from ceo_voice.voice.enums import ConstraintSeverity
from ceo_voice.voice.releases import HVMRelease


class ConstraintCompiler:
    """Compile independent rule sources into one canonical, conflict-free set."""

    def __init__(self, *, safety_constraints: tuple[CompiledConstraint, ...] = ()) -> None:
        if any(item.category is not ConstraintCategory.SAFETY for item in safety_constraints):
            raise ValueError("injected safety constraints must use the safety category")
        self._safety_constraints = safety_constraints

    def compile(
        self,
        release: HVMRelease,
        *,
        platform_contract: PlatformContract,
        language: str,
        audience: str,
        request_constraints: tuple[str, ...],
        user_constraints: tuple[UserConstraint, ...],
        compiled_at: datetime,
    ) -> ConstraintBundle:
        """Compile source-attributed constraints and reject irreconcilable hard rules."""

        constraints: list[CompiledConstraint] = [
            CompiledConstraint(
                constraint_id=f"platform.{platform_contract.platform.value}.maximum_characters",
                category=ConstraintCategory.PLATFORM,
                strength=ConstraintStrength.HARD,
                operator=ConstraintOperator.MAXIMUM,
                key="output.character_count",
                value=platform_contract.maximum_characters,
                priority=100,
                source=f"platform_contract:{platform_contract.version}",
                rationale="published output must fit the target platform contract",
            )
        ]
        constraints.extend(self._safety_constraints)
        for index, instruction in enumerate(request_constraints, start=1):
            constraints.append(
                CompiledConstraint(
                    constraint_id=f"request.instruction.{index}",
                    category=ConstraintCategory.USER,
                    strength=ConstraintStrength.SOFT,
                    operator=ConstraintOperator.INSTRUCTION,
                    key=f"user.instruction.{index}",
                    value=instruction,
                    priority=50,
                    source="generation_request",
                    rationale="legacy caller constraint preserved as an opaque soft instruction",
                )
            )
        constraints.extend(self._from_user(item) for item in user_constraints)
        for item in release.negative_constraints:
            if not item.effective_range.contains(compiled_at):
                continue
            if item.scope.language != language:
                continue
            if (
                item.scope.platform is not None
                and item.scope.platform is not platform_contract.platform
            ):
                continue
            if item.scope.audience is not None and item.scope.audience != audience:
                continue
            constraints.extend(self._from_negative(item))
        canonical = tuple(
            sorted(
                constraints,
                key=lambda item: (
                    -item.priority,
                    item.category.value,
                    item.key,
                    item.constraint_id,
                ),
            )
        )
        identifiers = tuple(item.constraint_id for item in canonical)
        if len(identifiers) != len(set(identifiers)):
            raise ContextCompilationError(
                "compiled constraint identifiers are not unique",
                details={"reason": "constraint_conflict"},
            )
        conflicts = self._find_conflicts(canonical)
        if conflicts:
            raise ContextCompilationError(
                "hard generation constraints conflict",
                details={"reason": "constraint_conflict", "conflicts": conflicts},
            )
        counts = Counter(item.category for item in canonical)
        return ConstraintBundle(
            constraints=canonical,
            summary=ConstraintSummary(
                total=len(canonical),
                hard=sum(item.strength is ConstraintStrength.HARD for item in canonical),
                soft=sum(item.strength is ConstraintStrength.SOFT for item in canonical),
                platform=counts[ConstraintCategory.PLATFORM],
                formatting=counts[ConstraintCategory.FORMATTING],
                user=counts[ConstraintCategory.USER],
                negative_voice=counts[ConstraintCategory.NEGATIVE_VOICE],
                safety=counts[ConstraintCategory.SAFETY],
            ),
        )

    @staticmethod
    def _from_user(item: UserConstraint) -> CompiledConstraint:
        return CompiledConstraint(
            constraint_id=item.constraint_id,
            category=item.category,
            strength=item.strength,
            operator=item.operator,
            key=item.key,
            value=item.value,
            priority=item.priority,
            source="typed_user_constraint",
            rationale=item.rationale,
        )

    @staticmethod
    def _from_negative(item: NegativeConstraint) -> tuple[CompiledConstraint, ...]:
        strength = (
            ConstraintStrength.HARD
            if item.severity is ConstraintSeverity.HARD
            else ConstraintStrength.SOFT
        )
        constraints: list[CompiledConstraint] = []
        trace_ids = tuple(
            sorted(
                (evidence.evidence_unit_id for evidence in item.evidence),
                key=lambda value: value.int,
            )
        )
        if item.prohibited_value is not None:
            constraints.append(
                CompiledConstraint(
                    constraint_id=f"voice.negative.{item.id}.value",
                    category=ConstraintCategory.NEGATIVE_VOICE,
                    strength=strength,
                    operator=ConstraintOperator.PROHIBIT,
                    key=f"voice.feature.{item.feature.feature_id}",
                    value=cast(JsonValue, item.prohibited_value.model_dump(mode="json")),
                    priority=90 if strength is ConstraintStrength.HARD else 70,
                    source=f"hvm_negative_constraint:{item.basis.value}",
                    rationale="governed HVM negative-space constraint",
                    trace_ids=(item.id, *trace_ids),
                )
            )
        if item.frequency_ceiling is not None:
            constraints.append(
                CompiledConstraint(
                    constraint_id=f"voice.negative.{item.id}.frequency",
                    category=ConstraintCategory.NEGATIVE_VOICE,
                    strength=strength,
                    operator=ConstraintOperator.MAXIMUM,
                    key=f"voice.feature.{item.feature.feature_id}.frequency",
                    value=item.frequency_ceiling,
                    priority=90 if strength is ConstraintStrength.HARD else 70,
                    source=f"hvm_negative_constraint:{item.basis.value}",
                    rationale="governed HVM feature-frequency ceiling",
                    trace_ids=(item.id, *trace_ids),
                )
            )
        return tuple(constraints)

    @classmethod
    def _find_conflicts(cls, constraints: tuple[CompiledConstraint, ...]) -> tuple[str, ...]:
        grouped: defaultdict[str, list[CompiledConstraint]] = defaultdict(list)
        for item in constraints:
            if item.strength is ConstraintStrength.HARD:
                grouped[item.key].append(item)
        conflicts: list[str] = []
        for key, items in sorted(grouped.items()):
            equals = [item for item in items if item.operator is ConstraintOperator.EQUALS]
            equal_values = {dumps_json(item.value) for item in equals}
            if len(equal_values) > 1:
                conflicts.append(f"{key}:multiple_equals")
                continue
            minimums = [
                cls._numeric(item) for item in items if item.operator is ConstraintOperator.MINIMUM
            ]
            maximums = [
                cls._numeric(item) for item in items if item.operator is ConstraintOperator.MAXIMUM
            ]
            if minimums and maximums and max(minimums) > min(maximums):
                conflicts.append(f"{key}:minimum_exceeds_maximum")
                continue
            if equals:
                equals_numeric = cls._optional_numeric(equals[0])
                if equals_numeric is not None:
                    if minimums and equals_numeric < max(minimums):
                        conflicts.append(f"{key}:equals_below_minimum")
                    if maximums and equals_numeric > min(maximums):
                        conflicts.append(f"{key}:equals_above_maximum")
                prohibited = {
                    dumps_json(item.value)
                    for item in items
                    if item.operator is ConstraintOperator.PROHIBIT
                }
                if dumps_json(equals[0].value) in prohibited:
                    conflicts.append(f"{key}:equals_prohibited")
        return tuple(conflicts)

    @staticmethod
    def _numeric(item: CompiledConstraint) -> float:
        value = ConstraintCompiler._optional_numeric(item)
        if value is None:
            raise ContextCompilationError(
                "numeric constraint operator requires a numeric value",
                details={
                    "reason": "unsupported_request",
                    "constraint_id": item.constraint_id,
                },
            )
        return value

    @staticmethod
    def _optional_numeric(item: CompiledConstraint) -> float | None:
        if isinstance(item.value, bool) or not isinstance(item.value, (int, float)):
            return None
        return float(item.value)
