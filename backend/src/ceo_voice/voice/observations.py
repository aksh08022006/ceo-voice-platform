"""Producer-neutral observation contracts; no feature extraction is implemented here."""

from typing import Self, cast
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.enums import MeasurementClass, ObservationState, ProducerType
from ceo_voice.voice.evidence import EvidenceReference
from ceo_voice.voice.primitives import (
    FeatureReference,
    ProducerReference,
    Sha256Digest,
    UnitInterval,
    VoiceContext,
)
from ceo_voice.voice.values import VoiceValue

_PRODUCER_FOR_MEASUREMENT = {
    MeasurementClass.DETERMINISTIC: ProducerType.DETERMINISTIC_SYSTEM,
    MeasurementClass.STATISTICAL: ProducerType.STATISTICAL_SYSTEM,
    MeasurementClass.PROBABILISTIC: ProducerType.PROBABILISTIC_MODEL,
    MeasurementClass.LLM_DERIVED: ProducerType.LLM_ANNOTATOR,
    MeasurementClass.HUMAN_ANNOTATED: ProducerType.HUMAN_REVIEWER,
}


class ObservationReference(ContractModel):
    """Content-addressed reference to one immutable observation."""

    observation_id: UUID = Field(description="Stable observation identifier.")
    content_hash: Sha256Digest = Field(description="Complete observation content digest.")


class Observation(ContractModel):
    """Immutable measured claim about one feature in one evidence-backed context.

    This object records what a producer asserted and how it was produced. It deliberately knows
    nothing about tokenization, parsers, LLM calls, statistical estimation, or human-review UI.
    """

    id: UUID = Field(description="Stable observation identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target identity associated with the observation.")
    feature: FeatureReference = Field(description="Exact feature definition measured.")
    context: VoiceContext = Field(description="Observed language and communication context.")
    measurement_class: MeasurementClass = Field(description="Observation production method.")
    state: ObservationState = Field(description="Observed value, abstention, or missingness.")
    value: VoiceValue | None = Field(description="Typed value when the state is observed.")
    quality: UnitInterval = Field(description="Calibrated producer-quality value.")
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, description="Addressable evidence and opportunity links."
    )
    producer: ProducerReference = Field(description="Exact producer lineage.")
    event_time: UtcDatetime = Field(description="Time of the observed source behavior.")
    created_at: UtcDatetime = Field(description="Time at which the observation was recorded.")

    @property
    def content_hash(self) -> str:
        """Return a deterministic digest of the complete observation payload."""

        payload = cast(JsonValue, self.model_dump(mode="json"))
        return sha256_text(dumps_json(payload))

    @property
    def reference(self) -> ObservationReference:
        """Return the content-addressed release reference for this observation."""

        return ObservationReference(observation_id=self.id, content_hash=self.content_hash)

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        """Enforce value-state, producer-class, and evidence-link invariants."""

        if self.state is ObservationState.OBSERVED and self.value is None:
            raise ValueError("observed observations require a typed value")
        if self.state is not ObservationState.OBSERVED and self.value is not None:
            raise ValueError("abstained or missing observations must not contain a value")
        expected_producer = _PRODUCER_FOR_MEASUREMENT[self.measurement_class]
        if self.producer.producer_type is not expected_producer:
            raise ValueError("producer type is incompatible with the measurement class")
        if (
            self.measurement_class is MeasurementClass.HUMAN_ANNOTATED
            and self.producer.actor_id is None
        ):
            raise ValueError("human-reviewed observations require an actor identifier")
        links = tuple((reference.evidence_unit_id, reference.role) for reference in self.evidence)
        if len(links) != len(set(links)):
            raise ValueError("observation evidence links must be unique by unit and role")
        return self
