"""End-to-end, incremental, publication, and recovery workflow tests."""

import asyncio

import pytest

from ceo_voice.core.exceptions import ProfileBuildError, StorageError
from ceo_voice.profiles import (
    BuildStage,
    InMemoryProfileWorkspace,
    ProfileBuildPolicy,
    ProgressEvent,
    ProgressKind,
    PublishedVoiceProfile,
    ScalarBaselineSnapshot,
    Tier1Runtime,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.voice import ReleaseStatus, ScalarValue, SourceModality
from tests.unit.profiles.factories import IDENTITY_ID, manifest


class ProgressCollector:
    """Capture progress events for workflow assertions."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    def report(self, event: ProgressEvent) -> None:
        self.events.append(event)


def test_builder_publishes_complete_hvm_profile_and_reports() -> None:
    workspace = InMemoryProfileWorkspace()
    progress = ProgressCollector()
    builder = create_tier1_profile_builder(workspace=workspace, progress=progress)

    profile = asyncio.run(builder.build(manifest(1, 2)))

    release = profile.managed_release.release
    assert profile.managed_release.status is ReleaseStatus.ACTIVE
    assert profile.validation_report.is_valid()
    assert release.version == 1
    assert len(profile.observations) == 76
    assert len(release.components.aggregates) == 38
    assert len(release.components.residuals) == 38
    assert len(release.components.conditional_residuals) == 38
    assert {
        item.confidence.independent_cluster_count for item in release.components.aggregates
    } == {2}
    assert {
        item.confidence.independent_cluster_count
        for item in release.components.conditional_residuals
    } == {2}
    assert profile.corpus_health.successful_documents == 2
    assert profile.corpus_health.observed_feature_count == 38
    assert profile.corpus_health.generation_ready is False
    assert profile.inspection.authority.value == "descriptive"
    assert "not an empirically calibrated" in profile.inspection.summary
    assert len(profile.retrieval_projection.indexed_features) == 38
    assert len(profile.retrieval_projection.indexed_component_ids) == 76
    assert {event.kind for event in progress.events} >= {
        ProgressKind.BUILD_STARTED,
        ProgressKind.DOCUMENT_ANALYZED,
        ProgressKind.COMPILATION_STARTED,
        ProgressKind.PUBLICATION_STARTED,
        ProgressKind.BUILD_COMPLETED,
    }
    assert asyncio.run(workspace.get_published(IDENTITY_ID, profile.corpus_hash)) == profile


def test_tier1_registry_evolves_additively_and_scopes_english_stance_features() -> None:
    runtime = build_tier1_runtime()

    assert (runtime.registry.version.major, runtime.registry.version.minor) == (1, 1)
    assert len(runtime.registry.definitions) == 38
    assert {
        (definition.semantic_version.major, definition.semantic_version.minor)
        for definition in runtime.registry.definitions
    } == {(1, 0)}
    first_person = runtime.registry.resolve_latest("analysis.opening-first-person-indicator")
    second_person = runtime.registry.resolve_latest("analysis.opening-second-person-indicator")
    assert first_person.supported_languages.languages == ("en",)
    assert second_person.supported_languages.languages == ("en",)
    assert first_person.supported_languages.all_languages is False


def test_identical_build_is_idempotent_and_incremental_build_reuses_documents() -> None:
    workspace = InMemoryProfileWorkspace()
    first_builder = create_tier1_profile_builder(workspace=workspace)
    first_manifest = manifest(1, 2)
    first = asyncio.run(first_builder.build(first_manifest))
    repeated = asyncio.run(first_builder.build(first_manifest))

    assert repeated == first
    second_progress = ProgressCollector()
    second_builder = create_tier1_profile_builder(workspace=workspace, progress=second_progress)
    second = asyncio.run(second_builder.build(manifest(1, 2, 3, day=20)))

    assert second.managed_release.status is ReleaseStatus.ACTIVE
    assert second.managed_release.release.version == 2
    assert second.managed_release.release.previous_release_id == first.managed_release.release.id
    lineage = asyncio.run(
        workspace.list_lineage(
            second.managed_release.release.tenant_id,
            second.managed_release.release.lineage_id,
        )
    )
    assert tuple(item.status for item in lineage) == (
        ReleaseStatus.SUPERSEDED,
        ReleaseStatus.ACTIVE,
    )
    assert second.corpus_health.reused_documents == 2
    assert sum(event.kind is ProgressKind.DOCUMENT_REUSED for event in second_progress.events) == 2
    assert (
        sum(event.kind is ProgressKind.DOCUMENT_ANALYZED for event in second_progress.events) == 1
    )


def test_compilation_input_change_cannot_return_a_stale_profile() -> None:
    workspace = InMemoryProfileWorkspace()
    runtime = build_tier1_runtime()
    first = asyncio.run(
        create_tier1_profile_builder(workspace=workspace, runtime=runtime).build(manifest(1))
    )
    original = runtime.baselines.baselines[0]
    changed = original.model_copy(
        update={
            "value": ScalarValue(value=1, unit=original.value.unit),
        }
    )
    changed_runtime = Tier1Runtime(
        registry=runtime.registry,
        analyzers=runtime.analyzers,
        baselines=ScalarBaselineSnapshot(baselines=(changed, *runtime.baselines.baselines[1:])),
    )

    second = asyncio.run(
        create_tier1_profile_builder(workspace=workspace, runtime=changed_runtime).build(
            manifest(1)
        )
    )

    assert second.corpus_hash != first.corpus_hash
    assert second.managed_release.release.version == 2


def test_non_publishing_build_stops_in_review_without_activation() -> None:
    workspace = InMemoryProfileWorkspace()
    builder = create_tier1_profile_builder(workspace=workspace)
    profile = asyncio.run(builder.build(manifest(1, publish=False)))

    assert profile.managed_release.status is ReleaseStatus.NEEDS_REVIEW
    assert profile.inspection.release_status is ReleaseStatus.NEEDS_REVIEW

    activated = asyncio.run(builder.build(manifest(1, publish=True)))
    assert activated.managed_release.status is ReleaseStatus.ACTIVE
    assert activated.managed_release.release.id == profile.managed_release.release.id
    assert activated.managed_release.release.version == 1


def test_unsupported_documents_are_isolated_or_blocked_by_explicit_policy() -> None:
    mixed = manifest(
        1,
        2,
        modalities=(SourceModality.AUTHORED_WRITTEN, SourceModality.MACHINE_TRANSCRIPT),
    )
    permissive = ProfileBuildPolicy(maximum_failed_fraction=0.75)
    profile = asyncio.run(
        create_tier1_profile_builder(workspace=InMemoryProfileWorkspace(), policy=permissive).build(
            mixed
        )
    )
    assert profile.corpus_health.failed_documents == 1
    assert profile.corpus_health.status.value == "warning"

    blocked_workspace = InMemoryProfileWorkspace()
    blocked = manifest(1, modalities=(SourceModality.MACHINE_TRANSCRIPT,))
    with pytest.raises(ProfileBuildError, match="does not satisfy"):
        asyncio.run(create_tier1_profile_builder(workspace=blocked_workspace).build(blocked))
    checkpoint = asyncio.run(
        blocked_workspace.get_checkpoint(IDENTITY_ID, _only_checkpoint_hash(blocked_workspace))
    )
    assert checkpoint is not None and checkpoint.stage is BuildStage.FAILED


def _only_checkpoint_hash(workspace: InMemoryProfileWorkspace) -> str:
    return next(iter(workspace._checkpoints))[1]


class FailOnceWorkspace(InMemoryProfileWorkspace):
    """Inject a post-publication artifact failure to exercise restart recovery."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    async def save_published(self, profile: PublishedVoiceProfile) -> None:
        if self.fail:
            self.fail = False
            raise StorageError("injected artifact failure")
        await super().save_published(profile)


def test_failed_build_resumes_existing_release_and_reuses_observations() -> None:
    workspace = FailOnceWorkspace()
    progress = ProgressCollector()
    builder = create_tier1_profile_builder(workspace=workspace, progress=progress)
    command = manifest(1, 2)

    with pytest.raises(StorageError, match="injected"):
        asyncio.run(builder.build(command))
    recovered = asyncio.run(builder.build(command))

    assert recovered.managed_release.status is ReleaseStatus.ACTIVE
    assert recovered.managed_release.release.version == 1
    assert recovered.corpus_health.reused_documents == 2
    assert any(event.kind is ProgressKind.BUILD_FAILED for event in progress.events)


class BrokenProgress:
    def report(self, event: ProgressEvent) -> None:
        del event
        raise RuntimeError("progress unavailable")


def test_progress_adapter_failure_does_not_control_build_correctness() -> None:
    profile = asyncio.run(
        create_tier1_profile_builder(
            workspace=InMemoryProfileWorkspace(), progress=BrokenProgress()
        ).build(manifest(1))
    )
    assert profile.managed_release.status is ReleaseStatus.ACTIVE
