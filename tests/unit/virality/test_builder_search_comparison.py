"""End-to-end publication, search, comparison, validation, and persistence tests."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import StorageError
from ceo_voice.models.enums import Platform
from ceo_voice.virality import (
    AggregationPolicy,
    FeatureReference,
    InMemoryViralityWorkspace,
    JsonViralityWorkspace,
    PatternAuthority,
    PatternChangeStatus,
    PatternSearcher,
    PatternSearchQuery,
    PublicationStatus,
    StructuralDimension,
    Version,
    ViralityReleaseValidator,
    compare_releases,
    create_virality_builder,
)
from ceo_voice.virality.features import build_feature_registry
from tests.unit.virality.factories import LIBRARY_ID, corpus


def test_builder_publishes_supported_voice_independent_release() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(1, 2, 3, 4)))
    release = profile.publication.release
    analysis = asyncio.run(workspace.get_analysis(release.analysis_snapshot))

    assert profile.publication.status is PublicationStatus.ACTIVE
    assert profile.publication.validation.is_valid()
    assert release.version == 1
    assert analysis is not None and len(analysis.observations) == 36
    assert release.analysis_snapshot.observation_count == 36
    assert len(release.patterns) == 9
    assert all(item.support_count == 4 for item in release.patterns)
    assert all(item.leader_count == 2 for item in release.patterns)
    assert all(item.authority is PatternAuthority.DESCRIPTIVE for item in release.patterns)
    assert profile.inspection.corpus_documents == 4
    assert profile.inspection.corpus_leaders == 2
    assert "no personal voice representation" in profile.inspection.summary
    assert not any("voice" in item.feature.feature_id for item in release.patterns)


def test_build_is_idempotent_and_incremental_release_supersedes_previous() -> None:
    workspace = InMemoryViralityWorkspace()
    builder = create_virality_builder(workspace=workspace)
    first = asyncio.run(builder.build(corpus(1, 2, 3, 4)))
    repeated = asyncio.run(builder.build(corpus(1, 2, 3, 4)))
    second = asyncio.run(builder.build(corpus(1, 2, 3, 4, 5, corpus_number=2)))

    assert repeated == first
    assert second.publication.release.version == 2
    assert second.publication.release.previous_release_id == first.publication.release.id
    history = asyncio.run(workspace.list_releases(first.publication.release.tenant_id, LIBRARY_ID))
    assert tuple(item.publication.status for item in history) == (
        PublicationStatus.SUPERSEDED,
        PublicationStatus.ACTIVE,
    )


def test_build_identity_is_order_independent_and_pins_performance_snapshot() -> None:
    workspace = InMemoryViralityWorkspace()
    builder = create_virality_builder(workspace=workspace)
    original_corpus = corpus(1, 2, 3, 4)
    first = asyncio.run(builder.build(original_corpus))
    reordered = original_corpus.model_copy(update={"items": tuple(reversed(original_corpus.items))})
    repeated = asyncio.run(builder.build(reordered))
    changed_metrics = original_corpus.model_copy(
        update={
            "items": (
                original_corpus.items[0].model_copy(
                    update={
                        "performance": original_corpus.items[0].performance.model_copy(
                            update={"reactions": 999}
                        )
                    }
                ),
                *original_corpus.items[1:],
            )
        }
    )
    second = asyncio.run(builder.build(changed_metrics))

    assert repeated == first
    assert second.build_fingerprint != first.build_fingerprint
    assert second.publication.release.corpus_hash != first.publication.release.corpus_hash
    assert second.publication.release.version == 2


def test_release_size_is_bounded_by_analysis_snapshot_and_audit_samples() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(*range(1, 31))))
    release = profile.publication.release
    analysis = asyncio.run(workspace.get_analysis(release.analysis_snapshot))

    assert analysis is not None and len(analysis.observations) == 270
    assert release.analysis_snapshot.observation_count == 270
    assert all(item.support_count == 30 for item in release.patterns)
    assert all(len(item.supporting_observation_ids) == 25 for item in release.patterns)
    assert "observations" not in release.model_dump()


def test_pattern_search_is_faceted_explainable_and_support_aware() -> None:
    profile = asyncio.run(
        create_virality_builder(workspace=InMemoryViralityWorkspace()).build(corpus(1, 2, 3, 4))
    )
    hits = PatternSearcher().search(
        profile.publication.release,
        PatternSearchQuery(
            platform=Platform.LINKEDIN,
            dimensions=(StructuralDimension.OPENING_HOOK,),
            minimum_support=4,
            authority=PatternAuthority.DESCRIPTIVE,
        ),
    )

    assert {item.pattern.feature.feature_id for item in hits} == {
        "structure.hook-type",
        "structure.opening-length",
    }
    assert all("4 posts from 2 leaders" in item.explanation for item in hits)
    assert (
        PatternSearcher().search(
            profile.publication.release, PatternSearchQuery(minimum_support=99)
        )
        == ()
    )


def test_release_comparison_reports_added_and_changed_patterns() -> None:
    workspace = InMemoryViralityWorkspace()
    builder = create_virality_builder(workspace=workspace)
    first = asyncio.run(builder.build(corpus(1, 2, 3, 4)))
    announcement = (
        "Today we are launching Atlas.\n\n"
        "It gives teams one place to plan.\n\n"
        "Read more at the link."
    )
    second = asyncio.run(
        builder.build(
            corpus(
                1,
                2,
                3,
                4,
                5,
                corpus_number=2,
                contents=(None, None, None, None, announcement),
            )
        )
    )
    report = compare_releases(
        first.publication.release,
        second.publication.release,
        compared_at=second.publication.published_at,
    )

    assert {item.status for item in report.changes} >= {
        PatternChangeStatus.ADDED,
        PatternChangeStatus.CHANGED,
    }
    assert any(item.pattern_key == "announcement" for item in report.changes)
    with pytest.raises(ValueError, match="one tenant and library"):
        compare_releases(
            first.publication.release,
            second.publication.release.model_copy(update={"library_id": UUID(int=999)}),
            compared_at=second.publication.published_at,
        )


def test_json_workspace_round_trips_catalog_and_supersession(tmp_path: Path) -> None:
    workspace = JsonViralityWorkspace(tmp_path)
    builder = create_virality_builder(workspace=workspace)
    first = asyncio.run(builder.build(corpus(1, 2, 3, 4)))
    second = asyncio.run(builder.build(corpus(1, 2, 3, 4, 5, corpus_number=2)))
    reloaded = JsonViralityWorkspace(tmp_path)
    history = asyncio.run(reloaded.list_releases(first.publication.release.tenant_id, LIBRARY_ID))

    assert len(history) == 2
    assert history[0].publication.status is PublicationStatus.SUPERSEDED
    assert history[1] == second
    assert (
        asyncio.run(reloaded.get_analysis(second.publication.release.analysis_snapshot)) is not None
    )


def test_validation_detects_content_and_aggregate_tampering() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(1, 2, 3, 4)))
    release = profile.publication.release
    analysis = asyncio.run(workspace.get_analysis(release.analysis_snapshot))
    assert analysis is not None
    pattern = release.patterns[0].model_copy(update={"support_count": 999})
    tampered = release.model_copy(
        update={"patterns": (pattern, *release.patterns[1:]), "content_hash": "f" * 64}
    )
    report = ViralityReleaseValidator(build_feature_registry()).validate(
        tampered, analysis, validated_at=profile.publication.published_at
    )

    assert not report.is_valid()
    assert {item.code.value for item in report.issues} >= {"aggregate", "version"}


def test_validation_reports_cross_reference_and_ownership_failures() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(1, 2, 3, 4)))
    release = profile.publication.release
    analysis = asyncio.run(workspace.get_analysis(release.analysis_snapshot))
    assert analysis is not None
    first_observation = analysis.observations[0]
    invalid_observation = first_observation.model_copy(
        update={
            "tenant_id": UUID(int=999),
            "pattern_key": "not-registered",
            "extractor_id": "wrong-producer",
            "evidence_ids": (UUID(int=998),),
        }
    )
    unknown_observation = analysis.observations[1].model_copy(
        update={
            "feature": FeatureReference(
                feature_id="structure.unknown",
                version=Version(major=1, minor=0, patch=0),
            )
        }
    )
    first_pattern = release.patterns[0].model_copy(
        update={
            "tenant_id": UUID(int=999),
            "supporting_observation_ids": (UUID(int=997),),
        }
    )
    second_pattern = release.patterns[1].model_copy(
        update={
            "feature": release.patterns[0].feature,
            "support_count": 999,
            "leader_count": 999,
            "supporting_evidence_ids": (UUID(int=996),),
            "authority": PatternAuthority.INSUFFICIENT,
        }
    )
    tampered_release = release.model_copy(
        update={
            "registry": release.registry.model_copy(update={"snapshot_hash": "e" * 64}),
            "patterns": (first_pattern, second_pattern, *release.patterns[2:]),
        }
    )
    tampered_analysis = analysis.model_copy(
        update={
            "observations": (
                invalid_observation,
                unknown_observation,
                *analysis.observations[2:],
                unknown_observation,
            ),
            "evidence": (*analysis.evidence, analysis.evidence[0]),
        }
    )
    report = ViralityReleaseValidator(build_feature_registry()).validate(
        tampered_release,
        tampered_analysis,
        validated_at=profile.publication.published_at,
    )

    assert not report.is_valid()
    assert {item.code.value for item in report.issues} >= {
        "ownership",
        "registry",
        "evidence",
        "observation",
        "aggregate",
        "version",
    }


def test_support_policy_prevents_single_leader_generalization() -> None:
    policy = AggregationPolicy(minimum_documents=2, minimum_leaders=2)
    profile = asyncio.run(
        create_virality_builder(workspace=InMemoryViralityWorkspace(), policy=policy).build(
            corpus(2, 4)
        )
    )

    assert all(
        item.authority is PatternAuthority.INSUFFICIENT
        for item in profile.publication.release.patterns
    )
    assert any("cross-document" in item for item in profile.inspection.limitations)


def test_workspace_rejects_release_identity_conflicts() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(1, 2, 3, 4)))
    conflict = profile.model_copy(update={"build_fingerprint": "a" * 64})
    with pytest.raises(StorageError, match="identity conflict"):
        asyncio.run(workspace.publish(conflict))


def test_production_virality_package_has_no_voice_domain_dependency() -> None:
    package = Path(__file__).parents[3] / "backend" / "src" / "ceo_voice" / "virality"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "ceo_voice.voice" not in source
    assert "VoiceFeature" not in source
