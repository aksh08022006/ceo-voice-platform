"""Synthetic corpora and an explicit showcase-only review gate."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.profiles import CuratedCorpus, CuratedDocument, ProfileBuildManifest
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.virality import (
    MetricCollectionMethod,
    PerformanceMetrics,
    Version,
    ViralityCorpus,
    ViralityCorpusItem,
)
from ceo_voice.voice import (
    DecisionState,
    FeatureRegistry,
    ProfileLineage,
    SemanticVersion,
    SourceModality,
    TargetIdentityType,
    VoiceIdentity,
)

from .catalog import ShowcaseProfile

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
TENANT_ID = uuid5(NAMESPACE_URL, "ceo-voice:showcase")


def _uuid(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ceo-voice:showcase:{value}")


def _digest(number: int) -> str:
    return format(number % 16, "x") * 64


def _document(
    profile: ShowcaseProfile,
    number: int,
    content: str,
    *,
    platform: Platform = Platform.LINKEDIN,
) -> CleanDocument:
    leader_id = _uuid(f"leader:{profile.slug}")
    return CleanDocument(
        id=_uuid(f"document:{profile.slug}:{number}"),
        raw_document_id=_uuid(f"raw:{profile.slug}:{number}"),
        tenant_id=TENANT_ID,
        ceo_id=leader_id,
        external_id=f"showcase-{profile.slug}-{number}",
        source=(DocumentSourceType.X if platform is Platform.X else DocumentSourceType.LINKEDIN),
        document_type=DocumentType.SOCIAL_POST,
        author=profile.name,
        platform=platform,
        publication_date=NOW + timedelta(days=number),
        title=f"Synthetic showcase document {number}",
        content=content,
        metadata={"thread_length": 1, "synthetic_showcase": True},
        transformation_lineage={"showcase-fixture": "1.0.0"},
        language="en",
        url=f"https://example.invalid/showcase/{profile.slug}/{number}",
        tags=("synthetic-showcase",),
        raw_checksum=_digest(number),
        source_fingerprint=_digest(number + 1),
        content_checksum=_digest(number + 2),
        document_fingerprint=_digest(number + 3),
        fetched_at=NOW,
        processed_at=NOW,
        source_version="showcase-1",
        version=1,
    )


def profile_manifest(profile: ShowcaseProfile) -> ProfileBuildManifest:
    """Create a governed point-in-time manifest from synthetic prose."""

    contents = (
        "Clear ownership creates speed.\n\nStart with the operating problem, then make the decision explicit.",
        "A platform matters when builders can use it.\n\nExplain the mechanism. Show the consequence.",
        "Useful systems earn trust through evidence.\n\nAvoid hype and make the limitation visible.",
        "The strongest teams connect ambition to execution.\n\nEnd with the next practical question.",
    )
    identity = VoiceIdentity(
        id=_uuid(f"identity:{profile.slug}"),
        tenant_id=TENANT_ID,
        leader_id=_uuid(f"leader:{profile.slug}"),
        display_name=profile.name,
        target_type=TargetIdentityType.PERSONAL_AUTHORSHIP,
        policy_version=SemanticVersion.parse("1.0.0"),
        created_at=NOW,
    )
    lineage = ProfileLineage(
        id=_uuid(f"lineage:{profile.slug}"),
        tenant_id=TENANT_ID,
        voice_identity_id=identity.id,
        lineage_policy_version=SemanticVersion.parse("1.0.0"),
        created_at=NOW,
    )
    return ProfileBuildManifest(
        corpus=CuratedCorpus(
            identity=identity,
            lineage=lineage,
            documents=tuple(
                CuratedDocument(
                    document=_document(
                        profile,
                        number,
                        content,
                        platform=Platform.X if number % 2 == 0 else Platform.LINKEDIN,
                    ),
                    source_modality=SourceModality.AUTHORED_WRITTEN,
                )
                for number, content in enumerate(contents, start=1)
            ),
        ),
        actor_id=_uuid("showcase-reviewer"),
        requested_at=NOW + timedelta(days=10),
        publish=True,
    )


def virality_corpus(profile: ShowcaseProfile) -> ViralityCorpus:
    """Create a multi-author structural corpus scoped to the showcase tenant."""

    items = []
    for number in range(1, 9):
        document = _document(
            profile,
            20 + number,
            (
                "Why do strong teams ship consistently?\n\n"
                "The problem is unclear ownership.\n\n"
                "Make one decision explicit.\n\nWhat would you change?"
            ),
            platform=Platform.X if number % 2 == 0 else Platform.LINKEDIN,
        ).model_copy(update={"ceo_id": _uuid(f"benchmark-leader:{(number // 2) % 2}")})
        items.append(
            ViralityCorpusItem(
                document=document,
                performance=PerformanceMetrics(
                    reactions=20 + number,
                    comments=4,
                    shares=2,
                    saves=3,
                    clicks=8,
                    impressions=2_000,
                    audience_size=10_000,
                    collected_at=NOW + timedelta(days=40),
                    method=MetricCollectionMethod.AUTHORIZED_EXPORT,
                ),
            )
        )
    return ViralityCorpus(
        id=_uuid(f"virality-corpus:{profile.slug}"),
        tenant_id=TENANT_ID,
        library_id=_uuid("virality-library"),
        dataset_version=Version(major=1, minor=0, patch=0),
        label="Synthetic showcase structural benchmark",
        items=tuple(items),
        created_at=NOW + timedelta(days=50),
    )


class ReviewedShowcaseProfileBuilder:
    """Promote only synthetic fixtures through an explicit local demonstration gate."""

    def __init__(self, builder: VoiceProfileBuilder, registry: FeatureRegistry) -> None:
        self._builder = builder
        self._registry = registry

    async def build(self, command: Any) -> Any:
        """Build normally, then attach synthetic review authorization for generation."""

        profile = await self._builder.build(command)
        release = profile.managed_release.release

        def promoted(value: Any) -> Any:
            return value.model_copy(
                update={
                    "measurement_reliability": 1,
                    "attribution_reliability": 1,
                    "coverage": 1,
                    "effective_support": min(1, value.evidence_count),
                    "context_diversity": 1,
                    "stability": 1,
                    "cross_context_robustness": 1,
                    "nuisance_robustness": 1,
                    "distinctiveness": 1,
                    "freshness": 1,
                    "calibration": 1,
                    "independent_cluster_count": min(1, value.evidence_count),
                }
            )

        components = release.components.model_copy(
            update={
                field: tuple(
                    item.model_copy(
                        update={
                            "confidence": promoted(item.confidence),
                            "decision_state": DecisionState.ACTIONABLE_STRONG,
                        }
                    )
                    for item in getattr(release.components, field)
                )
                for field in ("aggregates", "residuals", "conditional_residuals")
            }
        )
        authorized = release.model_copy(
            update={"registry": self._registry.reference, "components": components}
        )
        report = profile.validation_report.model_copy(
            update={"release_content_hash": authorized.content_hash}
        )
        managed = profile.managed_release.model_copy(
            update={"release": authorized, "validation_report": report}
        )
        return profile.model_copy(
            update={
                "managed_release": managed,
                "validation_report": report,
                "corpus_health": profile.corpus_health.model_copy(
                    update={"generation_ready": True}
                ),
                "inspection": profile.inspection.model_copy(
                    update={"release_content_hash": authorized.content_hash}
                ),
                "retrieval_projection": profile.retrieval_projection.model_copy(
                    update={"release_content_hash": authorized.content_hash}
                ),
            }
        )
