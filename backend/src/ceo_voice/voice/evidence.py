"""Immutable evidence units, links, and corpus snapshots for the HVM domain."""

from typing import Self, cast
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.enums import EvidenceRole, EvidenceUnitType, SourceModality
from ceo_voice.voice.primitives import (
    LanguageTag,
    SemanticVersion,
    Sha256Digest,
    UnitInterval,
)


class EvidenceUnit(ContractModel):
    """Addressable span inside one immutable, versioned source document."""

    id: UUID = Field(description="Stable evidence-unit identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target identity associated with the evidence.")
    document_id: UUID = Field(description="Stable canonical document identifier.")
    document_version: int = Field(ge=1, description="Exact immutable document version.")
    segmentation_version: SemanticVersion = Field(description="Exact segmentation policy version.")
    unit_type: EvidenceUnitType = Field(description="Structural evidence-unit type.")
    start_offset: int = Field(ge=0, description="Inclusive Unicode character offset.")
    end_offset: int = Field(ge=1, description="Exclusive Unicode character offset.")
    span_checksum: Sha256Digest = Field(description="SHA-256 digest of the referenced span.")
    structural_position: NonEmptyStr | None = Field(
        default=None, description="Controlled document position when available."
    )
    language: LanguageTag = Field(description="BCP 47 language tag.")
    source: DocumentSourceType = Field(description="Source family of the immutable document.")
    source_modality: SourceModality = Field(description="Production modality of the span.")
    document_type: DocumentType = Field(description="Canonical content form.")
    platform: Platform | None = Field(default=None, description="Source platform when applicable.")
    publication_time: UtcDatetime | None = Field(
        default=None, description="Source publication time when known."
    )

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        """Reject empty or reversed spans."""

        if self.end_offset <= self.start_offset:
            raise ValueError("evidence-unit end offset must be greater than start offset")
        return self

    @property
    def content_hash(self) -> str:
        """Return a digest covering the complete immutable evidence-unit identity."""

        payload = cast(JsonValue, self.model_dump(mode="json"))
        return sha256_text(dumps_json(payload))

    def to_member(self) -> "EvidenceSnapshotMember":
        """Return the immutable identity fields pinned by an evidence snapshot."""

        return EvidenceSnapshotMember(
            evidence_unit_id=self.id,
            document_id=self.document_id,
            document_version=self.document_version,
            segmentation_version=self.segmentation_version,
            span_checksum=self.span_checksum,
            unit_content_hash=self.content_hash,
        )


class EvidenceSnapshotMember(ContractModel):
    """Content-addressable evidence-unit identity stored in a corpus manifest."""

    evidence_unit_id: UUID = Field(description="Evidence-unit identifier.")
    document_id: UUID = Field(description="Canonical document identifier.")
    document_version: int = Field(ge=1, description="Exact document version.")
    segmentation_version: SemanticVersion = Field(description="Exact segmentation version.")
    span_checksum: Sha256Digest = Field(description="Referenced span digest.")
    unit_content_hash: Sha256Digest = Field(
        description="Digest of the complete evidence-unit identity and provenance."
    )


class EvidenceSnapshotReference(ContractModel):
    """Content-addressed reference to an immutable evidence manifest."""

    snapshot_id: UUID = Field(description="Evidence snapshot identifier.")
    snapshot_hash: Sha256Digest = Field(description="Canonical manifest digest.")


class EvidenceSnapshot(ContractModel):
    """Immutable, canonical membership manifest for an HVM build."""

    id: UUID = Field(description="Stable evidence snapshot identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target identity represented by the manifest.")
    members: tuple[EvidenceSnapshotMember, ...] = Field(
        min_length=1, description="Canonical ordered evidence membership."
    )
    created_at: UtcDatetime = Field(description="UTC manifest creation time.")

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        """Require unique, deterministically ordered members."""

        identifiers = tuple(member.evidence_unit_id for member in self.members)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evidence snapshot members must be unique")
        if identifiers != tuple(sorted(identifiers, key=lambda item: item.int)):
            raise ValueError("evidence snapshot members must be ordered by identifier")
        return self

    @classmethod
    def build(
        cls,
        *,
        snapshot_id: UUID,
        tenant_id: UUID,
        voice_identity_id: UUID,
        evidence_units: tuple[EvidenceUnit, ...],
        created_at: UtcDatetime,
    ) -> Self:
        """Build a canonical manifest and verify tenant and identity ownership."""

        if not evidence_units:
            raise ValueError("an evidence snapshot requires at least one evidence unit")
        if any(unit.tenant_id != tenant_id for unit in evidence_units):
            raise ValueError("evidence units must share the snapshot tenant")
        if any(unit.voice_identity_id != voice_identity_id for unit in evidence_units):
            raise ValueError("evidence units must share the snapshot identity")
        units = sorted(evidence_units, key=lambda item: item.id.int)
        return cls(
            id=snapshot_id,
            tenant_id=tenant_id,
            voice_identity_id=voice_identity_id,
            members=tuple(unit.to_member() for unit in units),
            created_at=created_at,
        )

    @property
    def snapshot_hash(self) -> str:
        """Return a deterministic digest of manifest ownership and membership."""

        payload = cast(
            JsonValue,
            self.model_dump(
                mode="json",
                include={"id", "tenant_id", "voice_identity_id", "members"},
            ),
        )
        return sha256_text(dumps_json(payload))

    @property
    def reference(self) -> EvidenceSnapshotReference:
        """Return the content-addressed reference pinned by a release."""

        return EvidenceSnapshotReference(snapshot_id=self.id, snapshot_hash=self.snapshot_hash)


class EvidenceWeightComponents(ContractModel):
    """Decomposed evidence trust and relevance inputs; no opaque composite is stored."""

    target_attribution: UnitInterval = Field(description="Target-authorship confidence.")
    speaker_attribution: UnitInterval = Field(description="Target-speaker confidence.")
    source_reliability: UnitInterval = Field(description="Canonical-source reliability.")
    modality_admissibility: UnitInterval = Field(description="Feature/modality compatibility.")
    observation_quality: UnitInterval = Field(description="Producer observation quality.")
    independence: UnitInterval = Field(description="Independence from duplicate/campaign text.")
    context_relevance: UnitInterval = Field(description="Match to asserted context.")
    temporal_relevance: UnitInterval = Field(description="Relevance to the target regime.")
    rights_admissible: bool = Field(description="Hard downstream-rights gate.")


class EvidenceReference(ContractModel):
    """Typed relationship from an observation or assertion to one evidence unit."""

    evidence_unit_id: UUID = Field(description="Referenced immutable evidence unit.")
    role: EvidenceRole = Field(description="Role played by the evidence.")
    weight_components: EvidenceWeightComponents = Field(
        description="Explainable evidence weighting inputs."
    )
    independence_cluster_id: NonEmptyStr = Field(
        description="Duplicate/campaign dependence cluster."
    )
    opportunity_count: int = Field(
        ge=0, description="Number of applicable opportunities represented by this link."
    )

    @model_validator(mode="after")
    def validate_opportunity(self) -> Self:
        """Require a non-zero denominator for explicit opportunity evidence."""

        if self.role is EvidenceRole.OPPORTUNITY and self.opportunity_count == 0:
            raise ValueError("opportunity evidence requires a positive opportunity count")
        return self
