"""Immutable input bundle for complete HVM structural validation."""

from pydantic import Field

from ceo_voice.models.base import ContractModel
from ceo_voice.voice.evidence import EvidenceSnapshot, EvidenceUnit
from ceo_voice.voice.identity import ProfileLineage, VoiceIdentity
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.releases import HVMRelease


class ReleaseValidationSubject(ContractModel):
    """Complete read-only material required for structural HVM validation."""

    identity: VoiceIdentity = Field(description="Governed target writing identity.")
    lineage: ProfileLineage = Field(description="Release lineage.")
    release: HVMRelease = Field(description="Sealed release candidate.")
    evidence_snapshot: EvidenceSnapshot = Field(description="Pinned evidence manifest.")
    evidence_units: tuple[EvidenceUnit, ...] = Field(min_length=1)
    observations: tuple[Observation, ...] = Field(min_length=1)
    previous_release: HVMRelease | None = Field(
        default=None, description="Immediate predecessor for version validation."
    )
