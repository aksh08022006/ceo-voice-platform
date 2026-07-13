"""Candidate evaluation contracts."""

from uuid import UUID

from pydantic import Field, JsonValue

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import EvaluationStatus


class EvaluationMetric(ContractModel):
    """One versioned, interpretable quality measurement."""

    name: NonEmptyStr = Field(description="Stable metric identifier.")
    score: float = Field(ge=0, le=1, description="Normalized metric score.")
    passed: bool = Field(description="Whether the metric met its configured threshold.")
    explanation: str | None = Field(
        default=None,
        description="Safe, concise rationale for operators and diagnostics.",
    )
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Versioned metric diagnostics and provenance.",
    )


class EvaluationResult(ContractModel):
    """Aggregate evaluation record for one generated candidate."""

    candidate_id: UUID = Field(description="Candidate evaluated by this record.")
    status: EvaluationStatus = Field(description="Aggregate evaluation disposition.")
    metrics: tuple[EvaluationMetric, ...] = Field(
        default_factory=tuple,
        description="Independent measurements contributing to the disposition.",
    )
    evaluator_version: NonEmptyStr = Field(
        description="Version identifier for the evaluator configuration and logic."
    )
    created_at: UtcDatetime = Field(description="UTC evaluation timestamp.")
