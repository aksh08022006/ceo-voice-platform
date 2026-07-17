"""Self-validating deployment bundles for immutable published profile serving."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.models.base import ContractModel, NonEmptyStr
from ceo_voice.profiles import CuratedCorpus, PublishedVoiceProfile
from ceo_voice.utils.files import read_text_limited
from ceo_voice.virality import ViralityCorpus, ViralityProfile
from ceo_voice.virality.contracts import CorpusAnalysis
from ceo_voice.virality.releases import build_analysis_snapshot
from ceo_voice.voice import FeatureRegistry

_MAX_BUNDLE_BYTES = 200 * 1024 * 1024
_MAX_CATALOG_BYTES = 1024 * 1024


class PublishedProfileBundle(ContractModel):
    """Complete content-addressed deployment unit for one selectable leader profile."""

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: NonEmptyStr
    role: NonEmptyStr
    summary: NonEmptyStr
    artifact_status: Literal["published", "development"] = "published"
    voice_profile: PublishedVoiceProfile
    voice_corpus: CuratedCorpus
    virality_profile: ViralityProfile
    virality_analysis: CorpusAnalysis
    virality_corpus: ViralityCorpus
    feature_registry: FeatureRegistry

    @model_validator(mode="after")
    def validate_pins(self) -> Self:
        """Reject cross-tenant, cross-release, and cross-snapshot bundle assembly."""

        release = self.voice_profile.managed_release.release
        identity = self.voice_corpus.identity
        virality_release = self.virality_profile.publication.release
        if release.voice_identity_id != identity.id:
            raise ValueError("voice profile does not belong to the bundled identity")
        if release.lineage_id != self.voice_corpus.lineage.id:
            raise ValueError("voice profile does not belong to the bundled lineage")
        if release.registry != self.feature_registry.reference:
            raise ValueError("feature registry does not match the voice release")
        if not (
            release.tenant_id
            == identity.tenant_id
            == self.virality_corpus.tenant_id
            == virality_release.tenant_id
        ):
            raise ValueError("published profile bundle crosses tenant boundaries")
        snapshot = virality_release.analysis_snapshot
        if snapshot.corpus_id != self.virality_corpus.id:
            raise ValueError("virality release does not reference the bundled corpus")
        if (
            build_analysis_snapshot(
                snapshot_id=snapshot.id,
                analysis=self.virality_analysis,
                corpus_id=self.virality_corpus.id,
            )
            != snapshot
        ):
            raise ValueError("virality analysis does not match the published snapshot")
        return self


class PublishedProfileCatalogManifest(ContractModel):
    """Relative bundle locations loaded at production process startup."""

    schema_version: str = Field(pattern=r"^1\.0$")
    bundles: tuple[Path, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        for path in self.bundles:
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("published bundle paths must be confined relative paths")
        if len(self.bundles) != len(set(self.bundles)):
            raise ValueError("published bundle paths must be unique")
        return self


def load_published_profile_catalog(path: Path) -> tuple[PublishedProfileBundle, ...]:
    """Load and validate a confined catalog and every referenced immutable bundle."""

    catalog_path = path.expanduser().resolve()
    root = catalog_path.parent
    try:
        manifest = PublishedProfileCatalogManifest.model_validate_json(
            read_text_limited(catalog_path, max_bytes=_MAX_CATALOG_BYTES)
        )
        bundles = tuple(
            PublishedProfileBundle.model_validate_json(
                read_text_limited(_confined(root, relative), max_bytes=_MAX_BUNDLE_BYTES)
            )
            for relative in manifest.bundles
        )
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            "published profile catalog is invalid",
            details={"catalog": str(catalog_path)},
        ) from exc
    slugs = tuple(bundle.slug for bundle in bundles)
    if len(slugs) != len(set(slugs)):
        raise ConfigurationError(
            "published profile catalog contains duplicate slugs",
            details={"catalog": str(catalog_path)},
        )
    return bundles


def _confined(root: Path, relative: Path) -> Path:
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("published bundle path escapes the catalog directory")
    return resolved
