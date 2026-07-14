"""HVM-targeted voice fidelity and measurable stylometric comparison."""

from statistics import fmean
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.voice.enums import VoiceDimension

from .contracts import EvaluationInput, EvaluationMetric, EvaluationPolicy
from .enums import EvaluationDimension, MetricSource
from .metrics import metric
from .stylometry import (
    lexical_overlap,
    ngram_overlap,
    numeric_target,
    proportional_similarity,
    style_measurements,
)


class VoiceFidelityEvaluator:
    """Compare supported candidate measurements with compiled HVM feature targets."""

    def evaluate(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        content = value.draft.content
        thread = value.draft.thread
        actual = style_measurements(content, thread_posts=len(thread))
        feature_scores: list[float] = []
        feature_diagnostics: dict[str, float] = {}
        platform_scores: list[float] = []
        component_ids: list[UUID] = []
        for feature in value.retrieval.voice_features:
            target = numeric_target(feature.target_value)
            measured = actual.get(feature.feature_id)
            if target is None or measured is None:
                continue
            score = proportional_similarity(measured, target)
            feature_scores.append(score)
            feature_diagnostics[feature.feature_id] = score
            component_ids.extend(feature.component_ids)
            if feature.dimension is VoiceDimension.PLATFORM_ADAPTATION:
                platform_scores.append(score)
        voice_score = fmean(feature_scores) if feature_scores else 0
        evidence = tuple(
            item
            for item in value.retrieval.evidence
            if EvidencePurpose.VOICE_SUPPORT in item.purposes
        )
        references = tuple(item.content for item in evidence)
        lexical = lexical_overlap(content, references)
        copying = ngram_overlap(content, references)
        evidence_availability = len(evidence) / max(1, len(value.retrieval.voice_features))
        return (
            metric(
                "voice.hvm_feature_similarity",
                EvaluationDimension.VOICE_FIDELITY,
                voice_score,
                "Candidate Tier-1 measurements were compared with numeric compiled HVM targets.",
                policy,
                source=MetricSource.STYLOMETRIC,
                applicable=bool(feature_scores),
                evidence=tuple(component_ids),
                diagnostics={"feature_scores": cast(JsonValue, feature_diagnostics)},
            ),
            metric(
                "voice.feature_target_observability",
                EvaluationDimension.VOICE_FIDELITY,
                len(feature_scores) / max(1, len(value.retrieval.voice_features)),
                "The evaluator reports rather than invents measurements for unsupported HVM features.",
                policy,
            ),
            metric(
                "voice.platform_adaptation",
                EvaluationDimension.VOICE_FIDELITY,
                fmean(platform_scores) if platform_scores else 1,
                "Platform-adaptation HVM features were measured when present.",
                policy,
                source=MetricSource.STYLOMETRIC,
                applicable=bool(platform_scores),
            ),
            metric(
                "voice.evidence_lexical_support",
                EvaluationDimension.VOICE_FIDELITY,
                lexical,
                "Lexical overlap with selected voice evidence is descriptive and does not prove causal use.",
                policy,
                applicable=False,
                evidence=tuple(item.evidence_id for item in evidence),
                diagnostics={"overlap": lexical},
            ),
            metric(
                "voice.evidence_coverage",
                EvaluationDimension.VOICE_FIDELITY,
                min(1.0, evidence_availability),
                "Selected voice evidence coverage was measured against compiled voice features.",
                policy,
                evidence=tuple(item.evidence_id for item in evidence),
            ),
            metric(
                "voice.near_copy_safety",
                EvaluationDimension.VOICE_FIDELITY,
                1.0 if copying <= policy.maximum_copying_ngram_overlap else 0.0,
                "Four-token overlap checks that fidelity was not achieved by copying evidence.",
                policy,
                diagnostics={
                    "maximum_allowed": policy.maximum_copying_ngram_overlap,
                    "observed_overlap": copying,
                },
            ),
        )
