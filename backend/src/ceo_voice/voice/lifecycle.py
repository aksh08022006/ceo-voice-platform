"""Release lifecycle orchestration over an injected atomic event-stream catalog."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from ceo_voice.core.exceptions import ReleaseLifecycleError
from ceo_voice.models.base import ContractModel, UtcDatetime, normalize_utc_datetime
from ceo_voice.voice.enums import ReleaseEventType, ReleaseStatus
from ceo_voice.voice.ports import ReleaseCatalog
from ceo_voice.voice.releases import (
    HVMRelease,
    ManagedRelease,
    ReleaseChange,
    ReleaseEvent,
    ValidationReport,
)


class LifecycleCommand(ContractModel):
    """Caller-supplied deterministic identity, actor, and time for one lifecycle fact."""

    event_id: UUID = Field(description="Stable event identifier supplied by the caller.")
    actor_id: UUID = Field(description="Authorized actor or service identity.")
    occurred_at: UtcDatetime = Field(description="UTC lifecycle event time.")


class ReleaseManager:
    """Manage immutable release streams without owning their persistence implementation."""

    def __init__(self, *, catalog: ReleaseCatalog) -> None:
        self._catalog = catalog

    async def create(self, release: HVMRelease, *, command: LifecycleCommand) -> ManagedRelease:
        """Create the first lifecycle event for a new sealed release."""

        if await self._catalog.get(release.tenant_id, release.id) is not None:
            raise self._error("release already exists", release.id)
        lineage = await self._catalog.list_lineage(release.tenant_id, release.lineage_id)
        if any(item.release.version == release.version for item in lineage):
            raise self._error("release version already exists in the lineage", release.id)
        if release.version > 1:
            predecessor = next(
                (
                    item.release
                    for item in lineage
                    if item.release.id == release.previous_release_id
                ),
                None,
            )
            if predecessor is None:
                raise self._error("release predecessor is absent from the lineage", release.id)
            if predecessor.version + 1 != release.version:
                raise self._error(
                    "release predecessor is not the immediately preceding version", release.id
                )
        event = self._event(
            release_id=release.id,
            sequence=1,
            event_type=ReleaseEventType.CREATED,
            command=command,
        )
        record = ManagedRelease(release=release, events=(event,))
        await self._catalog.commit((ReleaseChange(record=record, expected_revision=None),))
        return record

    async def begin_validation(
        self, tenant_id: UUID, release_id: UUID, *, command: LifecycleCommand
    ) -> ManagedRelease:
        """Append validation start to a building release."""

        record = await self._required(tenant_id, release_id)
        self._require_status(record, ReleaseStatus.BUILDING)
        updated = self._append(record, ReleaseEventType.VALIDATION_STARTED, command)
        await self._commit_update(record, updated)
        return updated

    async def complete_validation(
        self,
        tenant_id: UUID,
        release_id: UUID,
        report: ValidationReport,
        *,
        command: LifecycleCommand,
    ) -> ManagedRelease:
        """Record a passed or failed structural report on a validating release."""

        record = await self._required(tenant_id, release_id)
        self._require_status(record, ReleaseStatus.VALIDATING)
        if report.id != record.release.validation_report_id or report.release_id != release_id:
            raise self._error("validation report does not belong to the release", release_id)
        event_type = (
            ReleaseEventType.VALIDATION_PASSED
            if report.is_valid()
            else ReleaseEventType.VALIDATION_FAILED
        )
        updated = self._append(
            record,
            event_type,
            command,
            validation_report_id=report.id,
            validation_report=report,
        )
        await self._commit_update(record, updated)
        return updated

    async def approve(
        self, tenant_id: UUID, release_id: UUID, *, command: LifecycleCommand
    ) -> ManagedRelease:
        """Approve a structurally valid release for later activation."""

        record = await self._required(tenant_id, release_id)
        self._require_status(record, ReleaseStatus.NEEDS_REVIEW)
        if record.validation_report is None or not record.validation_report.is_valid():
            raise self._error("only a structurally valid release can be approved", release_id)
        updated = self._append(record, ReleaseEventType.APPROVED, command)
        await self._commit_update(record, updated)
        return updated

    async def activate(
        self,
        tenant_id: UUID,
        release_id: UUID,
        *,
        activation: LifecycleCommand,
        supersession: LifecycleCommand | None,
    ) -> ManagedRelease:
        """Atomically activate an approved release and supersede the current active release."""

        target = await self._required(tenant_id, release_id)
        self._require_status(target, ReleaseStatus.APPROVED)
        lineage = await self._catalog.list_lineage(tenant_id, target.release.lineage_id)
        active = tuple(item for item in lineage if item.status is ReleaseStatus.ACTIVE)
        if len(active) > 1:
            raise self._error("lineage contains multiple active releases", release_id)
        changes: list[ReleaseChange] = []
        if active:
            if supersession is None:
                raise self._error(
                    "supersession command is required for the active release", release_id
                )
            if supersession.occurred_at != activation.occurred_at:
                raise self._error(
                    "activation and supersession must share one effective time", release_id
                )
            current = active[0]
            updated_current = self._append(
                current,
                ReleaseEventType.SUPERSEDED,
                supersession,
                related_release_id=target.release.id,
            )
            changes.append(
                ReleaseChange(record=updated_current, expected_revision=current.revision)
            )
        elif supersession is not None:
            raise self._error("supersession command supplied without an active release", release_id)
        updated_target = self._append(target, ReleaseEventType.ACTIVATED, activation)
        changes.append(ReleaseChange(record=updated_target, expected_revision=target.revision))
        await self._catalog.commit(tuple(changes))
        return updated_target

    async def rollback(
        self,
        tenant_id: UUID,
        target_release_id: UUID,
        *,
        reactivation: LifecycleCommand,
        supersession: LifecycleCommand,
    ) -> ManagedRelease:
        """Atomically reactivate a superseded release without changing its payload."""

        target = await self._required(tenant_id, target_release_id)
        self._require_status(target, ReleaseStatus.SUPERSEDED)
        lineage = await self._catalog.list_lineage(tenant_id, target.release.lineage_id)
        active = tuple(item for item in lineage if item.status is ReleaseStatus.ACTIVE)
        if len(active) != 1:
            raise self._error(
                "rollback requires exactly one current active release", target_release_id
            )
        current = active[0]
        if current.release.id == target_release_id:
            raise self._error("rollback target is already active", target_release_id)
        if reactivation.occurred_at != supersession.occurred_at:
            raise self._error(
                "rollback and supersession must share one effective time", target_release_id
            )
        updated_current = self._append(
            current,
            ReleaseEventType.SUPERSEDED,
            supersession,
            related_release_id=target_release_id,
        )
        updated_target = self._append(
            target,
            ReleaseEventType.ROLLED_BACK_TO,
            reactivation,
            related_release_id=current.release.id,
        )
        await self._catalog.commit(
            (
                ReleaseChange(record=updated_current, expected_revision=current.revision),
                ReleaseChange(record=updated_target, expected_revision=target.revision),
            )
        )
        return updated_target

    async def withdraw(
        self, tenant_id: UUID, release_id: UUID, *, command: LifecycleCommand
    ) -> ManagedRelease:
        """Withdraw a building, reviewable, approved, or active release."""

        record = await self._required(tenant_id, release_id)
        if record.status not in {
            ReleaseStatus.BUILDING,
            ReleaseStatus.NEEDS_REVIEW,
            ReleaseStatus.APPROVED,
            ReleaseStatus.ACTIVE,
        }:
            raise self._error("release cannot be withdrawn from its current state", release_id)
        updated = self._append(record, ReleaseEventType.WITHDRAWN, command)
        await self._commit_update(record, updated)
        return updated

    async def active_at(
        self, tenant_id: UUID, lineage_id: UUID, *, as_of: datetime
    ) -> HVMRelease | None:
        """Return the single release active at a point in time."""

        normalized = normalize_utc_datetime(as_of)
        lineage = await self._catalog.list_lineage(tenant_id, lineage_id)
        active = tuple(
            item.release for item in lineage if item.status_at(normalized) is ReleaseStatus.ACTIVE
        )
        if len(active) > 1:
            raise ReleaseLifecycleError(
                "lineage has multiple active releases at the requested time",
                details={"lineage_id": str(lineage_id), "as_of": normalized.isoformat()},
            )
        return active[0] if active else None

    async def _required(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease:
        record = await self._catalog.get(tenant_id, release_id)
        if record is None:
            raise self._error("release was not found", release_id)
        return record

    async def _commit_update(self, previous: ManagedRelease, updated: ManagedRelease) -> None:
        await self._catalog.commit(
            (ReleaseChange(record=updated, expected_revision=previous.revision),)
        )

    @staticmethod
    def _require_status(record: ManagedRelease, expected: ReleaseStatus) -> None:
        if record.status is not expected:
            raise ReleaseLifecycleError(
                "release is in an invalid state for this transition",
                details={
                    "release_id": str(record.release.id),
                    "expected": expected,
                    "actual": record.status,
                },
            )

    @staticmethod
    def _append(
        record: ManagedRelease,
        event_type: ReleaseEventType,
        command: LifecycleCommand,
        *,
        validation_report_id: UUID | None = None,
        related_release_id: UUID | None = None,
        validation_report: ValidationReport | None = None,
    ) -> ManagedRelease:
        if any(event.id == command.event_id for event in record.events):
            raise ReleaseLifecycleError(
                "release event identifier already exists in the stream",
                details={"release_id": str(record.release.id), "event_id": str(command.event_id)},
            )
        if command.occurred_at < record.events[-1].occurred_at:
            raise ReleaseLifecycleError(
                "release events cannot be backdated within an event stream",
                details={"release_id": str(record.release.id)},
            )
        event = ReleaseManager._event(
            release_id=record.release.id,
            sequence=record.revision + 1,
            event_type=event_type,
            command=command,
            validation_report_id=validation_report_id,
            related_release_id=related_release_id,
        )
        return ManagedRelease(
            release=record.release,
            events=(*record.events, event),
            validation_report=validation_report or record.validation_report,
        )

    @staticmethod
    def _event(
        *,
        release_id: UUID,
        sequence: int,
        event_type: ReleaseEventType,
        command: LifecycleCommand,
        validation_report_id: UUID | None = None,
        related_release_id: UUID | None = None,
    ) -> ReleaseEvent:
        return ReleaseEvent(
            id=command.event_id,
            release_id=release_id,
            sequence=sequence,
            event_type=event_type,
            actor_id=command.actor_id,
            occurred_at=command.occurred_at,
            validation_report_id=validation_report_id,
            related_release_id=related_release_id,
        )

    @staticmethod
    def _error(message: str, release_id: UUID) -> ReleaseLifecycleError:
        return ReleaseLifecycleError(message, details={"release_id": str(release_id)})
