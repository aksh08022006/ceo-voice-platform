"""Central structural observation pipeline with governed evidence construction."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.core.exceptions import ViralityError
from ceo_voice.models.base import UtcDatetime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.virality.contracts import (
    CorpusAnalysis,
    EvidenceSpan,
    ExtractionContext,
    StructuralObservation,
    ViralityCorpus,
)
from ceo_voice.virality.normalization import PerformanceNormalizer
from ceo_voice.virality.registry import ExtractorRegistry, StructuralFeatureRegistry


class StructuralObservationPipeline:
    """Convert canonical posts into evidence-backed, registry-valid observations."""

    def __init__(
        self,
        *,
        registry: StructuralFeatureRegistry,
        extractors: ExtractorRegistry,
        normalizer: PerformanceNormalizer,
    ) -> None:
        self._registry = registry
        self._extractors = extractors
        self._normalizer = normalizer

    def analyze(self, corpus: ViralityCorpus, *, created_at: UtcDatetime) -> CorpusAnalysis:
        """Analyze every post deterministically; invalid extractor output fails centrally."""

        evidence: dict[object, EvidenceSpan] = {}
        observations: list[StructuralObservation] = []
        performances = []
        for item in sorted(corpus.items, key=lambda value: value.document.id.int):
            document = item.document
            assert document.platform is not None
            performance = self._normalizer.normalize(item.performance)
            performances.append(performance)
            context = ExtractionContext(document=document, performance=performance)
            for extractor in self._extractors.extractors:
                for measurement in extractor.extract(context):
                    definition = self._registry.get(measurement.feature)
                    if measurement.feature not in extractor.specification.features:
                        raise ViralityError(
                            "extractor emitted an undeclared structural feature",
                            details={"feature_id": measurement.feature.feature_id},
                        )
                    if measurement.pattern_key not in definition.allowed_patterns:
                        raise ViralityError(
                            "extractor emitted a pattern outside the governed vocabulary",
                            details={
                                "feature_id": measurement.feature.feature_id,
                                "pattern_key": measurement.pattern_key,
                            },
                        )
                    if measurement.end > len(document.content):
                        raise ViralityError("structural evidence span exceeds document content")
                    span_text = document.content[measurement.start : measurement.end]
                    evidence_id = uuid5(
                        NAMESPACE_URL,
                        ":".join(
                            (
                                str(document.id),
                                str(document.version),
                                measurement.unit.value,
                                str(measurement.start),
                                str(measurement.end),
                            )
                        ),
                    )
                    evidence[evidence_id] = EvidenceSpan(
                        id=evidence_id,
                        tenant_id=corpus.tenant_id,
                        corpus_id=corpus.id,
                        document_id=document.id,
                        document_version=document.version,
                        unit=measurement.unit,
                        start=measurement.start,
                        end=measurement.end,
                        text_hash=sha256_text(span_text),
                    )
                    observation_id = uuid5(
                        NAMESPACE_URL,
                        ":".join(
                            (
                                str(corpus.id),
                                str(document.id),
                                str(document.version),
                                measurement.feature.feature_id,
                                str(measurement.feature.version),
                                measurement.pattern_key,
                                extractor.specification.extractor_id,
                                str(extractor.specification.version),
                            )
                        ),
                    )
                    observations.append(
                        StructuralObservation(
                            id=observation_id,
                            tenant_id=corpus.tenant_id,
                            corpus_id=corpus.id,
                            document_id=document.id,
                            document_version=document.version,
                            leader_id=document.ceo_id,
                            platform=document.platform,
                            publication_date=document.publication_date,
                            feature=measurement.feature,
                            pattern_key=measurement.pattern_key,
                            label=measurement.label,
                            evidence_ids=(evidence_id,),
                            performance=performance,
                            extractor_id=extractor.specification.extractor_id,
                            extractor_version=extractor.specification.version,
                            created_at=created_at,
                        )
                    )
        return CorpusAnalysis(
            observations=tuple(sorted(observations, key=lambda item: item.id.int)),
            evidence=tuple(sorted(evidence.values(), key=lambda item: item.id.int)),
            normalized_performance=tuple(performances),
        )
