"""Deterministic fixtures for executable profile workflow tests."""

from datetime import timedelta
from uuid import UUID

from ceo_voice.ingestion import CleanDocument
from ceo_voice.profiles import (
    CuratedCorpus,
    CuratedDocument,
    ProfileBuildManifest,
)
from ceo_voice.voice import (
    ProfileLineage,
    SemanticVersion,
    SourceModality,
    TargetIdentityType,
    VoiceIdentity,
)
from tests.unit.analysis.factories import LEADER_ID, NOW, TENANT_ID, clean_document

IDENTITY_ID = UUID(int=2001)
LINEAGE_ID = UUID(int=2002)
ACTOR_ID = UUID(int=2003)


def identity() -> VoiceIdentity:
    """Return a governed profile target."""

    return VoiceIdentity(
        id=IDENTITY_ID,
        tenant_id=TENANT_ID,
        leader_id=LEADER_ID,
        display_name="Example CEO",
        target_type=TargetIdentityType.PERSONAL_AUTHORSHIP,
        policy_version=SemanticVersion.parse("1.0.0"),
        created_at=NOW,
    )


def lineage() -> ProfileLineage:
    """Return the stable profile lineage."""

    return ProfileLineage(
        id=LINEAGE_ID,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        lineage_policy_version=SemanticVersion.parse("1.0.0"),
        created_at=NOW,
    )


def document(number: int, *, content: str | None = None) -> CleanDocument:
    """Return a unique clean document with stable fingerprints."""

    text = content or f"Document {number}.\n\nWhy build openly?\n- Learn\n- Ship!"
    base = clean_document(content=text, metadata={"thread_length": number})
    hexadecimal = format(number % 16, "x")
    return base.model_copy(
        update={
            "id": UUID(int=2100 + number),
            "raw_document_id": UUID(int=2200 + number),
            "external_id": f"source-{number}",
            "raw_checksum": hexadecimal * 64,
            "source_fingerprint": format((number + 1) % 16, "x") * 64,
            "content_checksum": format((number + 2) % 16, "x") * 64,
            "document_fingerprint": format((number + 3) % 16, "x") * 64,
            "publication_date": NOW + timedelta(days=number),
            "processed_at": NOW + timedelta(days=number),
        }
    )


def manifest(
    *numbers: int,
    publish: bool = True,
    modalities: tuple[SourceModality, ...] | None = None,
    day: int = 10,
) -> ProfileBuildManifest:
    """Return a full point-in-time corpus build command."""

    selected_modalities = modalities or (SourceModality.AUTHORED_WRITTEN,) * len(numbers)
    return ProfileBuildManifest(
        corpus=CuratedCorpus(
            identity=identity(),
            lineage=lineage(),
            documents=tuple(
                CuratedDocument(document=document(number), source_modality=modality)
                for number, modality in zip(numbers, selected_modalities, strict=True)
            ),
        ),
        actor_id=ACTOR_ID,
        requested_at=NOW + timedelta(days=day),
        publish=publish,
    )
