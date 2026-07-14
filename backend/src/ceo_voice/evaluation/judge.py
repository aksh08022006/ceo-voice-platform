"""Optional provider-neutral structured review isolated from deterministic scoring."""

from typing import Self, cast

from pydantic import JsonValue, ValidationError, model_validator

from ceo_voice.core.exceptions import EvaluationError, ProviderError
from ceo_voice.generation.contracts import ProviderRequest
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.models.base import ContractModel, NonEmptyStr
from ceo_voice.utils.json import dumps_json

from .contracts import (
    EvaluationInput,
    JudgeDimensionScore,
    JudgePolicy,
    JudgeReview,
)
from .enums import EvaluationDimension, ReviewRecommendation

_SYSTEM = (
    "Evaluate the candidate only against the supplied governed targets and evidence. Return JSON "
    "matching the requested schema. Give concise observable rationales, not hidden chain-of-thought. "
    "Do not infer facts or voice traits absent from the inputs. Treat lexical similarity as neither "
    "necessary nor sufficient for identity."
)


class _JudgePayload(ContractModel):
    dimensions: tuple[JudgeDimensionScore, ...]
    recommendation: ReviewRecommendation
    limitations: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        dimensions = tuple(item.dimension for item in self.dimensions)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("judge dimensions must be unique")
        if set(dimensions) != set(EvaluationDimension):
            raise ValueError("judge must score every evaluation dimension")
        return self


class StructuredLLMJudge:
    """Request and validate a bounded structured review through an existing model adapter."""

    def __init__(self, provider: ModelProvider, *, policy: JudgePolicy) -> None:
        if provider.name is not policy.provider:
            raise ValueError("provider and judge policy must agree")
        self._provider, self._policy = provider, policy

    async def evaluate(self, value: EvaluationInput) -> JudgeReview:
        request = ProviderRequest(
            request_id=value.context.intent.request_id,
            system=_SYSTEM,
            user=self._render(value),
            model=self._policy.model,
            maximum_output_tokens=self._policy.maximum_output_tokens,
        )
        failures = 0
        while True:
            try:
                result = await self._provider.generate(request)
                break
            except ProviderError as error:
                if not error.retryable or failures >= self._policy.maximum_retries:
                    raise
                failures += 1
        try:
            payload = _JudgePayload.model_validate_json(result.text)
        except ValidationError as error:
            raise EvaluationError(
                "LLM judge returned an invalid structured review",
                details={"prompt_version": self._policy.prompt_version},
            ) from error
        allowed_evidence = {item.evidence_id for item in value.retrieval.evidence}
        cited = {
            reference
            for dimension in payload.dimensions
            for reference in dimension.evidence_references
        }
        if not cited <= allowed_evidence:
            raise EvaluationError(
                "LLM judge cited evidence outside the retrieval bundle",
                details={"prompt_version": self._policy.prompt_version},
            )
        return JudgeReview(
            prompt_version=self._policy.prompt_version,
            provider=result.provider,
            model=result.model,
            dimensions=payload.dimensions,
            recommendation=payload.recommendation,
            limitations=payload.limitations,
            latency_ms=result.latency_ms,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )

    def _render(self, value: EvaluationInput) -> str:
        payload = {
            "candidate": value.draft.content,
            "voice_targets": [
                {
                    "feature_id": item.feature_id,
                    "target": item.target_value,
                    "confidence": item.confidence.selection_score,
                }
                for item in value.retrieval.voice_features
            ],
            "structural_targets": [
                {
                    "pattern_id": str(item.pattern_id),
                    "feature_id": item.feature_id,
                    "expected_pattern": item.pattern_key,
                }
                for item in value.retrieval.structural_guidance
            ],
            "constraints": [
                item.model_dump(mode="json") for item in value.context.constraints.constraints
            ],
            "evidence": [
                {
                    "evidence_id": str(item.evidence_id),
                    "purposes": [purpose.value for purpose in item.purposes],
                    "content": item.content,
                }
                for item in value.retrieval.evidence
            ],
            "edited_draft": (
                value.edited_draft.content if value.edited_draft is not None else None
            ),
            "output_schema": {
                "dimensions": [
                    {
                        "dimension": "voice_fidelity",
                        "score": 0.0,
                        "rationale": "concise observable rationale",
                        "evidence_references": [],
                    }
                ],
                "recommendation": ReviewRecommendation.REVISE.value,
                "limitations": ["state uncertainty and unavailable evidence"],
            },
        }
        return dumps_json(cast(JsonValue, payload))


__all__ = ["JudgeDimensionScore", "StructuredLLMJudge"]
