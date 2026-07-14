"""VKR-aligned deterministic structural classification and comparison."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.enums import DocumentSourceType, DocumentType
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.virality import ExtractionContext, NormalizedPerformance, Version
from ceo_voice.virality.enums import PerformanceBasis
from ceo_voice.virality.extractors import default_extractors

from .contracts import EvaluationInput, EvaluationMetric, EvaluationPolicy
from .enums import EvaluationDimension
from .metrics import metric


class StructuralFidelityEvaluator:
    """Reuse governed VKR extractors to classify the candidate without learning new patterns."""

    def evaluate(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        actual = classify_structure(value)
        metrics: list[EvaluationMetric] = []
        for guidance in value.retrieval.structural_guidance:
            observed = actual.get(guidance.feature_id)
            metrics.append(
                metric(
                    f"structure.{guidance.feature_id}",
                    EvaluationDimension.STRUCTURAL_FIDELITY,
                    float(observed == guidance.pattern_key),
                    "Candidate classification was compared with the exact selected VKR pattern.",
                    policy,
                    applicable=observed is not None,
                    evidence=guidance.supporting_evidence_ids,
                    diagnostics={
                        "expected_pattern": guidance.pattern_key,
                        "observed_pattern": observed,
                    },
                )
            )
        return tuple(metrics) or (
            metric(
                "structure.no_guidance",
                EvaluationDimension.STRUCTURAL_FIDELITY,
                0,
                "No structural guidance was available for evaluation.",
                policy,
                applicable=False,
            ),
        )


def classify_structure(value: EvaluationInput) -> dict[str, str]:
    content = value.draft.content
    digest = sha256_text(content)
    identifier = uuid5(NAMESPACE_URL, f"evaluation-document:{value.draft.id}:{digest}")
    document = CleanDocument(
        id=identifier,
        raw_document_id=identifier,
        tenant_id=value.context.intent.tenant_id,
        ceo_id=value.context.intent.leader_id,
        external_id=f"evaluation:{value.draft.id}",
        source=DocumentSourceType.FILE_UPLOAD,
        document_type=DocumentType.SOCIAL_POST,
        author="evaluation-candidate",
        platform=value.context.platform.platform,
        publication_date=None,
        title=None,
        content=content,
        metadata={"thread_length": len(value.draft.thread)},
        language=value.context.voice.language,
        url=None,
        tags=(),
        raw_checksum=digest,
        source_fingerprint=digest,
        content_checksum=digest,
        document_fingerprint=digest,
        fetched_at=value.evaluated_at,
        processed_at=value.evaluated_at,
        source_version=None,
        version=1,
    )
    performance = NormalizedPerformance(
        weighted_engagement=0,
        score_per_thousand=0,
        basis=PerformanceBasis.RAW_ENGAGEMENT,
        denominator=None,
        confounded=True,
        limitations=("evaluation classification does not use performance",),
        normalizer_version=Version(major=1, minor=0, patch=0),
    )
    context = ExtractionContext(document=document, performance=performance)
    return {
        measurement.feature.feature_id: measurement.pattern_key
        for extractor in default_extractors()
        for measurement in extractor.extract(context)
    }
