"""Behavior tests for sealed releases, lifecycle management, and retrieval contracts."""

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.core.exceptions import ReleaseLifecycleError
from ceo_voice.voice import (
    CompiledProfile,
    DecisionState,
    DownstreamPermission,
    HVMRelease,
    LifecycleCommand,
    ManagedRelease,
    ReleaseChange,
    ReleaseEvent,
    ReleaseEventType,
    ReleaseManager,
    ReleaseStatus,
    ResolutionSource,
    ResolutionStep,
    ResolvedComponentKind,
    ResolvedVoiceComponent,
    RetrievalProjection,
    RetrievalProjectionType,
    ScalarValue,
    SemanticVersion,
    ValidationCode,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    VoiceProfileQuery,
    VoiceProfileQueryResult,
    VoiceQueryKind,
)
from ceo_voice.voice.releases import derive_release_status
from tests.unit.voice.factories import (
    ACTOR_ID,
    IDENTITY_ID,
    LINEAGE_ID,
    NOW,
    RELEASE_ID,
    REPORT_ID,
    TENANT_ID,
    confidence,
    context,
    feature_definition,
    release,
    residual,
    validation_report,
)


class FakeReleaseCatalog:
    """Test-only atomic catalog that exercises the production persistence port."""

    def __init__(self) -> None:
        self.records: dict[UUID, ManagedRelease] = {}

    async def get(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease | None:
        record = self.records.get(release_id)
        if record is None or record.release.tenant_id != tenant_id:
            return None
        return record

    async def list_lineage(self, tenant_id: UUID, lineage_id: UUID) -> tuple[ManagedRelease, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self.records.values()
                    if record.release.tenant_id == tenant_id
                    and record.release.lineage_id == lineage_id
                ),
                key=lambda record: record.release.version,
            )
        )

    async def commit(self, changes: tuple[ReleaseChange, ...]) -> None:
        for change in changes:
            current = self.records.get(change.record.release.id)
            if change.expected_revision is None:
                if current is not None:
                    raise RuntimeError("create conflict")
            elif current is None or current.revision != change.expected_revision:
                raise RuntimeError("revision conflict")
        for change in changes:
            self.records[change.record.release.id] = change.record


def command(number: int, *, seconds: int) -> LifecycleCommand:
    """Return one deterministic lifecycle command."""

    return LifecycleCommand(
        event_id=UUID(int=1000 + number),
        actor_id=ACTOR_ID,
        occurred_at=NOW + timedelta(seconds=seconds),
    )


async def approve_release(
    manager: ReleaseManager,
    release_value: HVMRelease,
    report: ValidationReport,
    *,
    offset: int,
) -> ManagedRelease:
    """Advance a release through creation, validation, and approval."""

    await manager.create(release_value, command=command(offset, seconds=offset))
    await manager.begin_validation(
        TENANT_ID, release_value.id, command=command(offset + 1, seconds=offset + 1)
    )
    await manager.complete_validation(
        TENANT_ID,
        release_value.id,
        report,
        command=command(offset + 2, seconds=offset + 2),
    )
    return await manager.approve(
        TENANT_ID,
        release_value.id,
        command=command(offset + 3, seconds=offset + 3),
    )


def test_hvm_release_is_sealed_content_addressed_and_report_pinned() -> None:
    release_value = release()
    report = validation_report(release_value=release_value)
    compiled = CompiledProfile(release=release_value, validation_report=report)

    assert len(release_value.content_hash) == 64
    assert HVMRelease.model_validate_json(release_value.model_dump_json()) == release_value
    assert compiled.validation_report.is_valid()
    with pytest.raises(ValidationError):
        release_value.__setattr__("version", 2)
    with pytest.raises(ValidationError, match="report IDs"):
        CompiledProfile(
            release=release_value,
            validation_report=report.model_copy(update={"id": UUID(int=999)}),
        )


def test_release_and_event_models_reject_invalid_lineage_and_links() -> None:
    release_value = release()

    with pytest.raises(ValidationError, match="first release"):
        HVMRelease.model_validate(
            {**release_value.model_dump(), "previous_release_id": UUID(int=999)}
        )
    with pytest.raises(ValidationError, match="at least one aggregate"):
        HVMRelease.model_validate(
            {
                **release_value.model_dump(),
                "components": release_value.components.model_copy(update={"aggregates": ()}),
            }
        )
    with pytest.raises(ValidationError, match="report reference"):
        ReleaseEvent(
            id=UUID(int=500),
            release_id=RELEASE_ID,
            sequence=1,
            event_type=ReleaseEventType.VALIDATION_PASSED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        )


def test_release_model_rejects_every_sealed_payload_ambiguity() -> None:
    release_value = release()
    payload = release_value.model_dump()

    with pytest.raises(ValidationError, match="immediate predecessor"):
        HVMRelease.model_validate({**payload, "version": 2, "previous_release_id": None})
    with pytest.raises(ValidationError, match="leader residual"):
        HVMRelease.model_validate(
            {
                **payload,
                "components": release_value.components.model_copy(update={"residuals": ()}),
            }
        )
    with pytest.raises(ValidationError, match="observation IDs"):
        HVMRelease.model_validate(
            {
                **payload,
                "observation_references": release_value.observation_references * 2,
            }
        )
    with pytest.raises(ValidationError, match="globally unique"):
        HVMRelease.model_validate(
            {
                **payload,
                "components": release_value.components.model_copy(
                    update={
                        "residuals": (
                            residual().model_copy(
                                update={"id": release_value.components.aggregates[0].id}
                            ),
                        )
                    }
                ),
            }
        )
    with pytest.raises(ValidationError, match="share the release tenant"):
        HVMRelease.model_validate(
            {
                **payload,
                "components": release_value.components.model_copy(
                    update={
                        "aggregates": (
                            release_value.components.aggregates[0].model_copy(
                                update={"tenant_id": UUID(int=900)}
                            ),
                        )
                    }
                ),
            }
        )
    with pytest.raises(ValidationError, match="share the release identity"):
        HVMRelease.model_validate(
            {
                **payload,
                "components": release_value.components.model_copy(
                    update={
                        "aggregates": (
                            release_value.components.aggregates[0].model_copy(
                                update={"voice_identity_id": UUID(int=901)}
                            ),
                        )
                    }
                ),
            }
        )


def test_compiled_profile_rejects_wrong_release_hash_and_failed_report() -> None:
    release_value = release()
    report = validation_report(release_value=release_value)

    with pytest.raises(ValidationError, match="different release"):
        CompiledProfile(
            release=release_value,
            validation_report=report.model_copy(update={"release_id": UUID(int=902)}),
        )
    with pytest.raises(ValidationError, match="content hash"):
        CompiledProfile(
            release=release_value,
            validation_report=report.model_copy(update={"release_content_hash": "f" * 64}),
        )
    failed = report.model_copy(
        update={
            "issues": (
                ValidationIssue(
                    code=ValidationCode.SCHEMA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    path="release",
                    message="Invalid.",
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="structurally valid"):
        CompiledProfile(release=release_value, validation_report=failed)


def test_release_events_and_replay_reject_invalid_graphs() -> None:
    created = ReleaseEvent(
        id=UUID(int=910),
        release_id=RELEASE_ID,
        sequence=1,
        event_type=ReleaseEventType.CREATED,
        actor_id=ACTOR_ID,
        occurred_at=NOW,
    )
    with pytest.raises(ValidationError, match="related release"):
        ReleaseEvent(
            id=UUID(int=911),
            release_id=RELEASE_ID,
            sequence=2,
            event_type=ReleaseEventType.SUPERSEDED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        )
    with pytest.raises(ValidationError, match="itself"):
        ReleaseEvent(
            id=UUID(int=912),
            release_id=RELEASE_ID,
            sequence=2,
            event_type=ReleaseEventType.SUPERSEDED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
            related_release_id=RELEASE_ID,
        )
    invalid_first = created.model_copy(update={"event_type": ReleaseEventType.APPROVED})
    with pytest.raises(ValueError, match="begin with creation"):
        derive_release_status((invalid_first,))
    invalid_transition = created.model_copy(
        update={"id": UUID(int=913), "sequence": 2, "event_type": ReleaseEventType.ACTIVATED}
    )
    with pytest.raises(ValueError, match="invalid from release state"):
        derive_release_status((created, invalid_transition))


@pytest.mark.parametrize(
    ("events_update", "report_update", "message"),
    (
        ({"release_id": UUID(int=920)}, None, "managed release"),
        ({"id": UUID(int=921)}, None, "IDs must be unique"),
        ({"sequence": 3}, None, "contiguous"),
        ({"occurred_at": NOW - timedelta(seconds=1)}, None, "nondecreasing"),
        (None, "wrong_id", "does not match"),
        (None, "stale_hash", "stale release hash"),
        (None, "orphan_report", "presence must agree"),
    ),
)
def test_managed_release_rejects_corrupt_event_streams(
    events_update: dict[str, object] | None,
    report_update: str | None,
    message: str,
) -> None:
    release_value = release()
    created = ReleaseEvent(
        id=UUID(int=910),
        release_id=release_value.id,
        sequence=1,
        event_type=ReleaseEventType.CREATED,
        actor_id=ACTOR_ID,
        occurred_at=NOW,
    )
    events: tuple[ReleaseEvent, ...] = (created,)
    if events_update is not None:
        second = created.model_copy(update={"id": UUID(int=921), "sequence": 2})
        if "occurred_at" in events_update:
            second = second.model_copy(update=events_update)
        else:
            first = created.model_copy(update=events_update)
            events = (first, second)
        if "occurred_at" in events_update:
            events = (created, second)
    report: ValidationReport | None = None
    if report_update == "wrong_id":
        report = validation_report(release_value=release_value).model_copy(
            update={"id": UUID(int=922)}
        )
    elif report_update == "stale_hash":
        report = validation_report(release_value=release_value).model_copy(
            update={"release_content_hash": "f" * 64}
        )
    elif report_update == "orphan_report":
        report = validation_report(release_value=release_value)

    with pytest.raises(ValidationError, match=message):
        ManagedRelease(release=release_value, events=events, validation_report=report)


async def _exercise_activation_supersession_rollback_and_point_in_time() -> None:
    catalog = FakeReleaseCatalog()
    manager = ReleaseManager(catalog=catalog)
    first = release()
    first_report = validation_report(release_value=first)
    await approve_release(manager, first, first_report, offset=1)
    activated_first = await manager.activate(
        TENANT_ID,
        first.id,
        activation=command(10, seconds=10),
        supersession=None,
    )
    second_id = UUID(int=30)
    second_report_id = UUID(int=31)
    second = release(
        release_id=second_id,
        report_id=second_report_id,
        version=2,
        previous_release_id=first.id,
    )
    second_report = validation_report(release_value=second, report_id=second_report_id)
    await approve_release(manager, second, second_report, offset=20)
    with pytest.raises(ReleaseLifecycleError, match="share one effective time"):
        await manager.activate(
            TENANT_ID,
            second.id,
            activation=command(30, seconds=30),
            supersession=command(31, seconds=31),
        )
    activated_second = await manager.activate(
        TENANT_ID,
        second.id,
        activation=command(30, seconds=30),
        supersession=command(31, seconds=30),
    )

    assert activated_first.status is ReleaseStatus.ACTIVE
    assert catalog.records[first.id].status is ReleaseStatus.SUPERSEDED
    assert activated_second.status is ReleaseStatus.ACTIVE
    assert (
        await manager.active_at(TENANT_ID, LINEAGE_ID, as_of=NOW + timedelta(seconds=15)) == first
    )
    assert (
        await manager.active_at(TENANT_ID, LINEAGE_ID, as_of=NOW + timedelta(seconds=35)) == second
    )

    with pytest.raises(ReleaseLifecycleError, match="share one effective time"):
        await manager.rollback(
            TENANT_ID,
            first.id,
            reactivation=command(40, seconds=40),
            supersession=command(41, seconds=41),
        )
    rolled_back = await manager.rollback(
        TENANT_ID,
        first.id,
        reactivation=command(40, seconds=40),
        supersession=command(41, seconds=40),
    )

    assert rolled_back.status is ReleaseStatus.ACTIVE
    assert catalog.records[second.id].status is ReleaseStatus.SUPERSEDED
    assert (
        await manager.active_at(TENANT_ID, LINEAGE_ID, as_of=NOW + timedelta(seconds=45)) == first
    )


async def _exercise_invalid_transitions_and_event_time() -> None:
    catalog = FakeReleaseCatalog()
    manager = ReleaseManager(catalog=catalog)
    release_value = release()
    await manager.create(release_value, command=command(1, seconds=2))

    with pytest.raises(ReleaseLifecycleError, match="invalid state"):
        await manager.approve(TENANT_ID, release_value.id, command=command(2, seconds=3))
    with pytest.raises(ReleaseLifecycleError, match="identifier already exists"):
        await manager.begin_validation(TENANT_ID, release_value.id, command=command(1, seconds=3))
    with pytest.raises(ReleaseLifecycleError, match="backdated"):
        await manager.begin_validation(TENANT_ID, release_value.id, command=command(3, seconds=1))
    with pytest.raises(ReleaseLifecycleError, match="already exists"):
        await manager.create(release_value, command=command(4, seconds=4))
    with pytest.raises(ReleaseLifecycleError, match="not found"):
        await manager.begin_validation(TENANT_ID, UUID(int=999), command=command(5, seconds=5))

    duplicate_version = release(
        release_id=UUID(int=950),
        report_id=UUID(int=951),
    )
    with pytest.raises(ReleaseLifecycleError, match="version already exists"):
        await manager.create(duplicate_version, command=command(6, seconds=6))
    skipped_version = release(
        release_id=UUID(int=952),
        report_id=UUID(int=953),
        version=3,
        previous_release_id=release_value.id,
    )
    with pytest.raises(ReleaseLifecycleError, match="immediately preceding"):
        await manager.create(skipped_version, command=command(7, seconds=7))


async def _exercise_validation_failure_and_withdrawal() -> None:
    catalog = FakeReleaseCatalog()
    manager = ReleaseManager(catalog=catalog)
    release_value = release()
    await manager.create(release_value, command=command(1, seconds=1))
    await manager.begin_validation(TENANT_ID, release_value.id, command=command(2, seconds=2))
    invalid_report = ValidationReport(
        id=REPORT_ID,
        release_id=release_value.id,
        release_content_hash=release_value.content_hash,
        validator_version=SemanticVersion.parse("1.0.0"),
        issues=(
            ValidationIssue(
                code=ValidationCode.SCHEMA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                path="release",
                message="Invalid.",
            ),
        ),
        validated_at=NOW,
    )
    rejected = await manager.complete_validation(
        TENANT_ID,
        release_value.id,
        invalid_report,
        command=command(3, seconds=3),
    )
    assert rejected.status is ReleaseStatus.REJECTED

    other = release(
        release_id=UUID(int=60),
        report_id=UUID(int=61),
        version=2,
        previous_release_id=release_value.id,
    )
    await manager.create(other, command=command(10, seconds=10))
    withdrawn = await manager.withdraw(TENANT_ID, other.id, command=command(11, seconds=11))
    assert withdrawn.status is ReleaseStatus.WITHDRAWN


def test_release_manager_supports_activation_supersession_rollback_and_point_in_time() -> None:
    asyncio.run(_exercise_activation_supersession_rollback_and_point_in_time())


def test_release_manager_rejects_invalid_transitions_and_event_time() -> None:
    asyncio.run(_exercise_invalid_transitions_and_event_time())


def test_release_manager_records_validation_failure_and_withdrawal() -> None:
    asyncio.run(_exercise_validation_failure_and_withdrawal())


def test_retrieval_contracts_are_typed_release_pinned_and_serializable() -> None:
    feature = feature_definition().reference
    query = VoiceProfileQuery(
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        release_id=RELEASE_ID,
        kind=VoiceQueryKind.OPENING_STYLE,
        context=context(),
        dimensions=(),
        features=(feature,),
        downstream_use=DownstreamPermission.RETRIEVE,
        minimum_decision_state=DecisionState.DESCRIPTIVE,
        include_evidence_references=True,
        maximum_components=10,
    )
    resolved = ResolvedVoiceComponent(
        component_id=UUID(int=70),
        kind=ResolvedComponentKind.CORE_RESIDUAL,
        feature=feature,
        value=ScalarValue(value=0.1, unit="residual"),
        confidence=confidence(),
        decision_state=DecisionState.ACTIONABLE_SOFT,
        resolution_trace=(
            ResolutionStep(
                order=1,
                source=ResolutionSource.CORE_RESIDUAL,
                component_id=UUID(int=70),
                applied=True,
            ),
        ),
        evidence_unit_ids=(UUID(int=6),),
    )
    result = VoiceProfileQueryResult(
        query_id=UUID(int=71),
        release_id=RELEASE_ID,
        release_content_hash="a" * 64,
        components=(resolved,),
        resolved_at=NOW,
    )
    projection = RetrievalProjection(
        id=UUID(int=72),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        release_id=RELEASE_ID,
        release_content_hash="a" * 64,
        projection_type=RetrievalProjectionType.FEATURE_INDEX,
        indexed_features=(feature,),
        indexed_component_ids=(resolved.component_id,),
        projection_version=SemanticVersion.parse("1.0.0"),
        projection_hash="b" * 64,
        materialized_at=NOW,
    )

    assert VoiceProfileQuery.model_validate_json(query.model_dump_json()) == query
    assert VoiceProfileQueryResult.model_validate_json(result.model_dump_json()) == result
    assert projection.indexed_features == (feature,)
    with pytest.raises(ValidationError, match="exactly one"):
        VoiceProfileQuery.model_validate({**query.model_dump(), "as_of": NOW})
    with pytest.raises(ValidationError, match="contiguous"):
        ResolvedVoiceComponent.model_validate(
            {
                **resolved.model_dump(),
                "resolution_trace": (
                    ResolutionStep(
                        order=2,
                        source=ResolutionSource.CORE_RESIDUAL,
                        applied=True,
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="must be unique"):
        RetrievalProjection.model_validate(
            {**projection.model_dump(), "indexed_features": (feature, feature)}
        )
