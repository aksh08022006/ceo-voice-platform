"""Centralized conversion from analyzer candidates to valid HVM observations."""

from uuid import NAMESPACE_URL, UUID, uuid5

from ceo_voice.analysis.contracts import (
    AnalysisRequest,
    AnalyzedDocument,
    AnalyzerSpecification,
    ConfidenceRequest,
    MeasurementCandidate,
)
from ceo_voice.analysis.enums import ConfidenceMethod
from ceo_voice.analysis.ports import ConfidenceComposer
from ceo_voice.core.exceptions import FeatureRegistryError, ObservationBuildError
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.voice.enums import EvidenceRole, MeasurementClass, ProducerType
from ceo_voice.voice.evidence import EvidenceReference, EvidenceUnit
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.ports import FeatureRegistryReader
from ceo_voice.voice.primitives import ProducerReference, VoiceContext

_PRODUCER_TYPES = {
    MeasurementClass.DETERMINISTIC: ProducerType.DETERMINISTIC_SYSTEM,
    MeasurementClass.STATISTICAL: ProducerType.STATISTICAL_SYSTEM,
    MeasurementClass.PROBABILISTIC: ProducerType.PROBABILISTIC_MODEL,
    MeasurementClass.LLM_DERIVED: ProducerType.LLM_ANNOTATOR,
}


class ObservationBuilder:
    """The only analysis component authorized to construct HVM observations."""

    def __init__(
        self,
        *,
        feature_registry: FeatureRegistryReader,
        confidence_composer: ConfidenceComposer,
    ) -> None:
        self._feature_registry = feature_registry
        self._confidence_composer = confidence_composer

    def build(
        self,
        *,
        request: AnalysisRequest,
        analyzed_document: AnalyzedDocument,
        analyzer: AnalyzerSpecification,
        candidate: MeasurementCandidate,
        candidate_ordinal: int,
    ) -> tuple[Observation, tuple[EvidenceUnit, ...]]:
        """Validate and construct one observation plus all referenced evidence units."""

        if candidate.feature not in analyzer.supported_features:
            raise ObservationBuildError(
                "analyzer emitted an undeclared feature",
                details={"analyzer_id": analyzer.analyzer_id},
            )
        try:
            definition = self._feature_registry.get(candidate.feature)
        except FeatureRegistryError as exc:
            raise ObservationBuildError(
                "candidate feature is absent from the pinned registry",
                details={"feature_id": candidate.feature.feature_id},
            ) from exc
        if analyzer.measurement_class not in definition.measurement_pipeline:
            raise ObservationBuildError("analyzer measurement class is not registry-compatible")
        if candidate.value is not None and candidate.value.kind is not definition.value_type:
            raise ObservationBuildError("candidate value type does not match the feature registry")
        if request.source_modality not in definition.supported_modalities:
            raise ObservationBuildError("source modality is unsupported by the feature")
        if not (
            definition.supported_languages.all_languages
            or request.document.language in definition.supported_languages.languages
        ):
            raise ObservationBuildError("document language is unsupported by the feature")
        if not (
            definition.supported_platforms.all_platforms
            or request.document.platform in definition.supported_platforms.platforms
        ):
            raise ObservationBuildError("document platform is unsupported by the feature")

        try:
            spans = tuple(
                analyzed_document.span(span_id) for span_id in candidate.evidence_span_ids
            )
        except KeyError as exc:
            raise ObservationBuildError(
                "candidate references an unknown evidence span",
                details={"span_id": str(exc.args[0])},
            ) from exc
        if not any(span.unit_type is definition.observation_scope for span in spans):
            raise ObservationBuildError("candidate evidence does not include the feature scope")

        confidence = self._confidence_composer.compose(
            ConfidenceRequest(
                method=self._confidence_method(analyzer.measurement_class),
                measurement_class=analyzer.measurement_class,
                analyzer=analyzer,
                candidate=candidate,
                evidence_count=len(spans),
            )
        )
        evidence_units = tuple(
            self._evidence_unit(
                request=request, analyzed_document=analyzed_document, span_id=span.id
            )
            for span in spans
        )
        evidence_references = tuple(
            EvidenceReference(
                evidence_unit_id=unit.id,
                role=EvidenceRole.SUPPORT,
                weight_components=confidence.evidence_weights,
                independence_cluster_id=request.document.document_fingerprint,
                opportunity_count=candidate.opportunity_count,
            )
            for unit in evidence_units
        )
        observation_id = self._observation_id(
            request.run_id,
            analyzer.analyzer_id,
            candidate.feature.feature_id,
            candidate_ordinal,
        )
        observation = Observation(
            id=observation_id,
            tenant_id=request.document.tenant_id,
            voice_identity_id=request.voice_identity.id,
            feature=candidate.feature,
            context=VoiceContext(
                language=request.document.language,
                platform=request.document.platform,
                content_form=request.document.document_type,
            ),
            measurement_class=analyzer.measurement_class,
            state=candidate.state,
            value=candidate.value,
            quality=confidence.quality,
            evidence=evidence_references,
            producer=ProducerReference(
                producer_id=analyzer.analyzer_id,
                producer_type=_PRODUCER_TYPES[analyzer.measurement_class],
                version=analyzer.version,
                configuration_hash=analyzer.configuration_hash,
            ),
            event_time=request.event_time,
            created_at=request.created_at,
        )
        return observation, evidence_units

    @staticmethod
    def _confidence_method(measurement_class: MeasurementClass) -> ConfidenceMethod:
        if measurement_class is MeasurementClass.DETERMINISTIC:
            return ConfidenceMethod.DETERMINISTIC
        if measurement_class is MeasurementClass.STATISTICAL:
            return ConfidenceMethod.STATISTICAL
        if measurement_class is MeasurementClass.PROBABILISTIC:
            return ConfidenceMethod.CLASSIFIER
        if measurement_class is MeasurementClass.LLM_DERIVED:
            return ConfidenceMethod.LLM
        raise ObservationBuildError("human annotations are outside the analyzer framework")

    @staticmethod
    def _observation_id(
        run_id: UUID, analyzer_id: str, feature_id: str, candidate_ordinal: int
    ) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"{run_id}:{analyzer_id}:{feature_id}:{candidate_ordinal}",
        )

    @staticmethod
    def _evidence_unit(
        *, request: AnalysisRequest, analyzed_document: AnalyzedDocument, span_id: UUID
    ) -> EvidenceUnit:
        span = analyzed_document.span(span_id)
        position_parts = [f"ordinal:{span.ordinal}"]
        if span.paragraph_id is not None:
            position_parts.append(f"paragraph:{span.paragraph_id}")
        if span.sentence_id is not None:
            position_parts.append(f"sentence:{span.sentence_id}")
        return EvidenceUnit(
            id=span.id,
            tenant_id=request.document.tenant_id,
            voice_identity_id=request.voice_identity.id,
            document_id=request.document.id,
            document_version=request.document.version,
            segmentation_version=analyzed_document.segmentation_version,
            unit_type=span.unit_type,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
            span_checksum=sha256_text(analyzed_document.text_for(span)),
            structural_position=";".join(position_parts),
            language=request.document.language,
            source=request.document.source,
            source_modality=request.source_modality,
            document_type=request.document.document_type,
            platform=request.document.platform,
            publication_time=request.document.publication_date,
        )
