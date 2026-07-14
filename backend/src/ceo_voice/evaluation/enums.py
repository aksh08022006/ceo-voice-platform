"""Closed evaluation dimensions, metric sources, and failure taxonomy."""

from enum import StrEnum


class EvaluationDimension(StrEnum):
    VOICE_FIDELITY = "voice_fidelity"
    STRUCTURAL_FIDELITY = "structural_fidelity"
    CONSTRAINT_COMPLIANCE = "constraint_compliance"
    PLATFORM_COMPLIANCE = "platform_compliance"
    FACTUAL_PRESERVATION = "factual_preservation"
    EDIT_PRESERVATION = "edit_preservation"
    READABILITY = "readability"


class MetricSource(StrEnum):
    DETERMINISTIC = "deterministic"
    STYLOMETRIC = "stylometric"
    LLM_JUDGE = "llm_judge"
    HUMAN_REVIEW = "human_review"


class FailureCategory(StrEnum):
    VOICE_DRIFT = "voice_drift"
    CONSTRAINT_VIOLATION = "constraint_violation"
    PLATFORM_VIOLATION = "platform_violation"
    FACTUAL_RISK = "factual_risk"
    EDIT_DRIFT = "edit_drift"
    STRUCTURAL_MISALIGNMENT = "structural_misalignment"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_GENERATION = "unsupported_generation"
    READABILITY_DEGRADATION = "readability_degradation"
    JUDGE_DISAGREEMENT = "judge_disagreement"


class BenchmarkStatus(StrEnum):
    PASSED = "passed"
    REGRESSED = "regressed"


class ReviewRecommendation(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"
