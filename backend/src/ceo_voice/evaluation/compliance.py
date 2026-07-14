"""Constraint, platform, formatting, thread, and safety evaluation."""

from pydantic import JsonValue

from ceo_voice.context.enums import ConstraintOperator
from ceo_voice.prompts import THREAD_SEPARATOR

from .contracts import EvaluationInput, EvaluationMetric, EvaluationPolicy
from .enums import EvaluationDimension
from .metrics import metric

_UNSAFE = ("kill yourself", "racial slur")


class ComplianceEvaluator:
    """Evaluate only constraints whose semantics can be checked deterministically."""

    def evaluate(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        return (*self._platform(value, policy), *self._constraints(value, policy))

    def _platform(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        content = value.draft.content
        posts = tuple(item.strip() for item in content.split(THREAD_SEPARATOR) if item.strip())
        contract = value.context.platform
        maximum_post = max((len(item) for item in posts), default=0)
        thread_allowed = contract.thread_output_supported or len(posts) == 1
        thread_limit = contract.maximum_thread_posts
        return (
            metric(
                "platform.character_limit",
                EvaluationDimension.PLATFORM_COMPLIANCE,
                float(maximum_post <= contract.maximum_characters),
                "Every platform unit was checked against the compiled character limit.",
                policy,
                diagnostics={
                    "maximum_allowed": contract.maximum_characters,
                    "maximum_observed": maximum_post,
                },
            ),
            metric(
                "platform.thread_support",
                EvaluationDimension.PLATFORM_COMPLIANCE,
                float(thread_allowed),
                "Thread output was checked against platform capability.",
                policy,
                diagnostics={"observed_posts": len(posts)},
            ),
            metric(
                "platform.thread_limit",
                EvaluationDimension.PLATFORM_COMPLIANCE,
                float(thread_limit is None or len(posts) <= thread_limit),
                "Thread length was checked against the compiled platform contract.",
                policy,
                applicable=thread_limit is not None,
                diagnostics={"maximum_allowed": thread_limit, "observed_posts": len(posts)},
            ),
            metric(
                "platform.engine_validation",
                EvaluationDimension.PLATFORM_COMPLIANCE,
                float(value.draft.report.final_validation.valid),
                "The producing engine's independent final validation disposition was retained.",
                policy,
            ),
        )

    def _constraints(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        content = value.draft.content
        lowered = content.casefold()
        metrics: list[EvaluationMetric] = [
            metric(
                "constraint.safety_blocklist",
                EvaluationDimension.CONSTRAINT_COMPLIANCE,
                float(not any(term in lowered for term in _UNSAFE)),
                "Candidate text was checked against the versioned deterministic safety terms.",
                policy,
            )
        ]
        for constraint in value.context.constraints.constraints:
            if constraint.key == "output.character_count":
                continue
            supported, satisfied = self._evaluate_constraint(
                content, constraint.operator, constraint.value
            )
            metrics.append(
                metric(
                    f"constraint.{constraint.constraint_id}",
                    EvaluationDimension.CONSTRAINT_COMPLIANCE,
                    float(satisfied),
                    (
                        "Constraint was checked deterministically."
                        if supported
                        else "Constraint semantics are not deterministically observable from text."
                    ),
                    policy,
                    applicable=supported,
                    evidence=constraint.trace_ids,
                    diagnostics={
                        "operator": constraint.operator.value,
                        "strength": constraint.strength.value,
                        "key": constraint.key,
                    },
                )
            )
        return tuple(metrics)

    @staticmethod
    def _evaluate_constraint(
        content: str, operator: ConstraintOperator, raw_value: JsonValue
    ) -> tuple[bool, bool]:
        lowered = content.casefold()
        if operator is ConstraintOperator.INSTRUCTION and isinstance(raw_value, str):
            instruction = raw_value.strip()
            if instruction.casefold().startswith("must include:"):
                expected = instruction.split(":", 1)[1].strip().casefold()
                return True, expected in lowered
            if instruction.casefold().startswith("must not include:"):
                prohibited = instruction.split(":", 1)[1].strip().casefold()
                return True, prohibited not in lowered
        if operator is ConstraintOperator.PROHIBIT and isinstance(raw_value, str):
            return True, raw_value.casefold() not in lowered
        if operator is ConstraintOperator.EQUALS and isinstance(raw_value, str):
            return True, raw_value.casefold() in lowered
        if operator in {ConstraintOperator.MAXIMUM, ConstraintOperator.MINIMUM} and isinstance(
            raw_value, (int, float)
        ):
            satisfied = (
                len(content) <= raw_value
                if operator is ConstraintOperator.MAXIMUM
                else len(content) >= raw_value
            )
            return True, satisfied
        return False, True
