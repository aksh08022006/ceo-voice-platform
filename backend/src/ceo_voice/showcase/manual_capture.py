"""Build an explicitly development-only profile bundle from reviewed screenshot captures."""

import json
from collections.abc import Sequence
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError, model_validator

from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.profiles import (
    CuratedCorpus,
    CuratedDocument,
    JsonProfileWorkspace,
    ProfileBuildManifest,
    ReviewedDevelopmentProfileBuilder,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.services import PublishedProfileBundle, PublishedProfileCatalogManifest
from ceo_voice.utils.files import read_text_limited
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.utils.time import utc_now
from ceo_voice.virality import JsonViralityWorkspace, create_virality_builder
from ceo_voice.voice import DownstreamPermission, FeatureRegistry, SourceModality

from .catalog import ShowcaseProfile, profile_by_slug
from .fixtures import profile_manifest, virality_corpus

_MAX_CAPTURE_BYTES = 50 * 1024 * 1024
_MINIMUM_COMPLETE_POSTS = 20


class ScreenshotCapture(ContractModel):
    """One operator-reviewed transcription from a supported social-platform screenshot."""

    capture_id: NonEmptyStr
    leader_name: NonEmptyStr
    platform: Platform
    content: NonBlankText
    visible_date: str | None = None
    content_type: NonEmptyStr
    is_complete: bool
    is_repost: bool
    is_quote_post: bool
    quoted_content: str | None = None
    uncertain_spans: tuple[str, ...] = ()
    capture_notes: str | None = None

    @model_validator(mode="after")
    def validate_capture(self) -> "ScreenshotCapture":
        if self.platform not in {Platform.LINKEDIN, Platform.X}:
            raise ValueError("screenshot development profiles support only LinkedIn and X")
        if self.is_quote_post and self.quoted_content is None:
            raise ValueError("quote posts require separately identified quoted content")
        if self.quoted_content is not None and not (self.is_quote_post or self.is_repost):
            raise ValueError("quoted content is valid only for a quote post or repost")
        return self


def load_manual_capture_manifest(
    *,
    profile_slug: str,
    capture_paths: Sequence[Path],
    requested_at: UtcDatetime | None = None,
) -> ProfileBuildManifest:
    """Convert complete, reviewed captures into deterministic clean documents.

    Missing URLs and absolute publication timestamps remain missing. The loader never fabricates
    either value and never includes quoted third-party text. Complete repost commentary remains
    eligible because it is authored voice evidence; its repost status is retained in metadata.
    """

    profile = profile_by_slug(profile_slug)
    captures = _load_captures(capture_paths)
    ids = tuple(item.capture_id for item in captures)
    if len(ids) != len(set(ids)):
        raise ValueError("manual capture IDs must be unique across the complete corpus")
    if any(item.leader_name.casefold() != profile.name.casefold() for item in captures):
        raise ValueError("manual captures do not match the selected leader")
    admitted = tuple(item for item in captures if item.is_complete)
    if len(admitted) < _MINIMUM_COMPLETE_POSTS:
        raise ValueError(
            f"manual development profile requires at least {_MINIMUM_COMPLETE_POSTS} complete posts"
        )
    base = profile_manifest(profile)
    timestamp = requested_at or utc_now()
    documents = tuple(
        CuratedDocument(
            document=_clean_document(profile, base, capture, timestamp),
            source_modality=SourceModality.AUTHORED_WRITTEN,
        )
        for capture in admitted
    )
    return ProfileBuildManifest(
        corpus=CuratedCorpus(
            identity=base.corpus.identity,
            lineage=base.corpus.lineage,
            documents=documents,
        ),
        actor_id=base.actor_id,
        requested_at=timestamp,
        publish=True,
    )


async def publish_manual_capture_bundle(
    *,
    profile_slug: str,
    capture_paths: Sequence[Path],
    workspace_root: Path,
    catalog_path: Path,
) -> PublishedProfileBundle:
    """Build HVM/VKR artifacts and atomically publish one local development catalog."""

    profile = profile_by_slug(profile_slug)
    manifest = load_manual_capture_manifest(
        profile_slug=profile_slug,
        capture_paths=capture_paths,
    )
    runtime = build_tier1_runtime()
    registry = _generation_registry(runtime.registry)
    workspace = workspace_root.expanduser().resolve()
    voice_profile = await ReviewedDevelopmentProfileBuilder(
        create_tier1_profile_builder(
            workspace=JsonProfileWorkspace(workspace),
            runtime=runtime,
        ),
        registry,
    ).build(manifest)
    structural_corpus = virality_corpus(profile)
    virality_workspace = JsonViralityWorkspace(workspace)
    virality_profile = await create_virality_builder(workspace=virality_workspace).build(
        structural_corpus
    )
    analysis = await virality_workspace.get_analysis(
        virality_profile.publication.release.analysis_snapshot
    )
    if analysis is None:
        raise RuntimeError("development VKR analysis was not persisted")
    bundle = PublishedProfileBundle(
        slug=profile.slug,
        name=profile.name,
        role=profile.role,
        summary=(
            f"Development-only profile built from {len(manifest.corpus.documents)} complete "
            "screenshot-transcribed social posts. Provenance remains incomplete."
        ),
        artifact_status="development",
        voice_profile=voice_profile,
        voice_corpus=manifest.corpus,
        virality_profile=virality_profile,
        virality_analysis=analysis,
        virality_corpus=structural_corpus,
        feature_registry=registry,
    )
    resolved_catalog = catalog_path.expanduser().resolve()
    bundle_path = resolved_catalog.parent / f"{profile.slug}.json"
    _atomic_write(bundle_path, bundle.model_dump_json(indent=2))
    existing_paths: tuple[Path, ...] = ()
    if resolved_catalog.exists():
        existing = PublishedProfileCatalogManifest.model_validate_json(
            read_text_limited(resolved_catalog, max_bytes=1024 * 1024)
        )
        existing_paths = tuple(path for path in existing.bundles if path != Path(bundle_path.name))
    catalog = PublishedProfileCatalogManifest(
        schema_version="1.0",
        bundles=tuple(sorted((*existing_paths, Path(bundle_path.name)), key=str)),
    )
    _atomic_write(resolved_catalog, catalog.model_dump_json(indent=2))
    return bundle


def _load_captures(paths: Sequence[Path]) -> tuple[ScreenshotCapture, ...]:
    if not paths:
        raise ValueError("at least one capture file is required")
    captures: list[ScreenshotCapture] = []
    for path in paths:
        payload = json.loads(read_text_limited(path, max_bytes=_MAX_CAPTURE_BYTES))
        if not isinstance(payload, list):
            raise ValueError("capture files must contain a JSON array")
        try:
            captures.extend(ScreenshotCapture.model_validate(item) for item in payload)
        except ValidationError:
            raise
    return tuple(captures)


def _clean_document(
    profile: ShowcaseProfile,
    base: ProfileBuildManifest,
    capture: ScreenshotCapture,
    timestamp: UtcDatetime,
) -> CleanDocument:
    content_hash = sha256_text(capture.content)
    source_hash = sha256_text(f"{capture.capture_id}:{capture.content}")
    document_hash = sha256_text(
        dumps_json(
            {
                "capture_id": capture.capture_id,
                "content_hash": content_hash,
                "platform": capture.platform.value,
                "visible_date": capture.visible_date,
            }
        )
    )
    return CleanDocument(
        id=uuid5(NAMESPACE_URL, f"ceo-voice:manual-capture:document:{capture.capture_id}"),
        raw_document_id=uuid5(NAMESPACE_URL, f"ceo-voice:manual-capture:raw:{capture.capture_id}"),
        tenant_id=base.corpus.identity.tenant_id,
        ceo_id=base.corpus.identity.leader_id,
        external_id=capture.capture_id,
        source=(
            DocumentSourceType.X if capture.platform is Platform.X else DocumentSourceType.LINKEDIN
        ),
        document_type=DocumentType.SOCIAL_POST,
        author=profile.name,
        platform=capture.platform,
        publication_date=None,
        title=None,
        content=capture.content,
        metadata={
            "acquisition_method": "manual_capture",
            "capture_medium": "screenshot_ocr",
            "visible_date": capture.visible_date,
            "development_only": True,
            "content_type": capture.content_type,
            "is_repost": capture.is_repost,
            "is_quote_post": capture.is_quote_post,
            "quoted_content_excluded": capture.quoted_content is not None,
            "uncertain_span_count": len(capture.uncertain_spans),
        },
        transformation_lineage={"manual-screenshot-capture": "1.0.0"},
        language="en",
        url=None,
        tags=(
            "manual-capture",
            "development-only",
            capture.content_type,
            *(("repost-commentary",) if capture.is_repost else ()),
        ),
        raw_checksum=content_hash,
        source_fingerprint=source_hash,
        content_checksum=content_hash,
        document_fingerprint=document_hash,
        fetched_at=timestamp,
        processed_at=timestamp,
        source_version=f"screenshot:{capture.visible_date or 'unknown'}",
        version=1,
    )


def _generation_registry(source: FeatureRegistry) -> FeatureRegistry:
    return FeatureRegistry.build(
        registry_id=source.id,
        version=source.version,
        definitions=tuple(
            item.model_copy(
                update={
                    "downstream_permissions": tuple(
                        dict.fromkeys((*item.downstream_permissions, DownstreamPermission.GENERATE))
                    )
                }
            )
            for item in source.definitions
        ),
        created_at=source.created_at,
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
