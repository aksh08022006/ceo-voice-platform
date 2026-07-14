"""Immutable Virality Knowledge Release construction and content addressing."""

from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ceo_voice.models.base import UtcDatetime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.virality.contracts import (
    AggregationPolicy,
    AnalysisSnapshot,
    CorpusAnalysis,
    PatternAggregate,
    RegistryReference,
    ViralityRelease,
)


def build_release(
    *,
    release_id: UUID,
    tenant_id: UUID,
    library_id: UUID,
    version: int,
    previous_release_id: UUID | None,
    corpus_id: UUID,
    corpus_hash: str,
    registry: RegistryReference,
    policy: AggregationPolicy,
    analysis_snapshot: AnalysisSnapshot,
    patterns: tuple[PatternAggregate, ...],
    created_at: UtcDatetime,
) -> ViralityRelease:
    """Build and hash one complete immutable VKR snapshot."""

    candidate = ViralityRelease(
        id=release_id,
        tenant_id=tenant_id,
        library_id=library_id,
        version=version,
        previous_release_id=previous_release_id,
        corpus_id=corpus_id,
        corpus_hash=corpus_hash,
        registry=registry,
        aggregation_policy=policy,
        analysis_snapshot=analysis_snapshot,
        patterns=patterns,
        created_at=created_at,
        content_hash="0" * 64,
    )
    return candidate.model_copy(update={"content_hash": release_content_hash(candidate)})


def release_content_hash(release: ViralityRelease) -> str:
    """Hash every immutable release field except the digest itself."""

    payload = cast(JsonValue, release.model_dump(mode="json", exclude={"content_hash"}))
    return sha256_text(dumps_json(payload))


def build_analysis_snapshot(
    *, snapshot_id: UUID, analysis: CorpusAnalysis, corpus_id: UUID
) -> AnalysisSnapshot:
    """Content-address a full observation dataset independently from its compact release."""

    payload = cast(JsonValue, analysis.model_dump(mode="json"))
    return AnalysisSnapshot(
        id=snapshot_id,
        corpus_id=corpus_id,
        observation_count=len(analysis.observations),
        evidence_count=len(analysis.evidence),
        content_hash=sha256_text(dumps_json(payload)),
    )
