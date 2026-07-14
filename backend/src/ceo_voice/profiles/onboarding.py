"""Manifest-driven onboarding across existing HVM and VKR builders."""

from pathlib import Path

from pydantic import Field

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.profiles.contracts import ProfileBuildManifest
from ceo_voice.virality import ViralityCorpus, ViralityLibraryBuilder


class OnboardingManifest(ContractModel):
    """All reviewed inputs required to onboard one leader without changing code."""

    profile: ProfileBuildManifest
    virality: ViralityCorpus


class OnboardingReport(ContractModel):
    """Machine-readable readiness decision over the two published knowledge releases."""

    leader_name: NonEmptyStr
    voice_release_id: str
    voice_release_version: int = Field(ge=1)
    virality_release_id: str
    virality_release_version: int = Field(ge=1)
    corpus_documents: int = Field(ge=1)
    virality_documents: int = Field(ge=1)
    generation_ready: bool
    readiness_reason: NonEmptyStr
    completed_at: UtcDatetime


class CEOOnboardingService:
    """Coordinate the existing builders and publish a single readiness report."""

    def __init__(
        self,
        *,
        profile_builder: VoiceProfileBuilder,
        virality_builder: ViralityLibraryBuilder,
    ) -> None:
        self._profile_builder = profile_builder
        self._virality_builder = virality_builder

    async def onboard(self, manifest: OnboardingManifest) -> OnboardingReport:
        """Build both releases and report, without weakening generation governance."""

        identity = manifest.profile.corpus.identity
        if manifest.virality.tenant_id != identity.tenant_id:
            raise ValueError("voice and virality corpora must share a tenant")
        profile = await self._profile_builder.build(manifest.profile)
        virality = await self._virality_builder.build(manifest.virality)
        ready = profile.corpus_health.generation_ready
        reason = (
            "profile passed the configured generation-authority gates"
            if ready
            else "profile is descriptive; human review and calibrated analyzers are required"
        )
        return OnboardingReport(
            leader_name=identity.display_name,
            voice_release_id=str(profile.managed_release.release.id),
            voice_release_version=profile.managed_release.release.version,
            virality_release_id=str(virality.publication.release.id),
            virality_release_version=virality.publication.release.version,
            corpus_documents=len(manifest.profile.corpus.documents),
            virality_documents=len(manifest.virality.items),
            generation_ready=ready,
            readiness_reason=reason,
            completed_at=manifest.profile.requested_at,
        )


def write_onboarding_report(report: OnboardingReport, workspace: Path) -> Path:
    """Atomically persist the report below the caller-selected workspace."""

    destination = workspace.expanduser().resolve() / "onboarding" / "report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(destination)
    return destination
