"""Validation, incremental-decision, persistence, and run outcome contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.ingestion.contracts import ConnectorCheckpoint
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime


class ValidationSeverity(StrEnum):
    """Severity assigned to an ingestion validation issue."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(ContractModel):
    """One machine-readable validation finding."""

    code: NonEmptyStr = Field(description="Stable issue code.")
    message: NonEmptyStr = Field(description="Safe operator-facing explanation.")
    severity: ValidationSeverity = Field(description="Whether processing must stop.")
    field: str | None = Field(default=None, description="Related field when applicable.")


class ValidationResult(ContractModel):
    """Complete non-short-circuiting validation result for one artifact."""

    is_valid: bool = Field(description="Whether no error-severity findings were produced.")
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple,
        description="All validation findings in deterministic order.",
    )


class RepositoryWriteDisposition(StrEnum):
    """Outcome of an idempotent repository write."""

    CREATED = "created"
    UPDATED = "updated"
    ALREADY_EXISTS = "already_exists"


class DocumentChangeKind(StrEnum):
    """Incremental-processing decision for a source item."""

    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"


class DocumentChangeDecision(ContractModel):
    """Auditable incremental decision made before or after normalization."""

    kind: DocumentChangeKind = Field(description="Required processing disposition.")
    next_version: int | None = Field(
        default=None,
        ge=1,
        description="Version to persist for new or changed content.",
    )
    existing_document_id: UUID | None = Field(
        default=None,
        description="Related stored document for changed, unchanged, or duplicate content.",
    )
    existing_version: int | None = Field(
        default=None,
        ge=1,
        description="Version of the related stored document.",
    )
    reason: NonEmptyStr = Field(description="Stable human-readable decision rationale.")

    @model_validator(mode="after")
    def validate_version_semantics(self) -> Self:
        """Require a write version only for decisions that continue processing."""

        if self.kind in {DocumentChangeKind.NEW, DocumentChangeKind.CHANGED}:
            if self.next_version is None:
                raise ValueError("new and changed decisions require next_version")
        elif self.next_version is not None:
            raise ValueError("unchanged and duplicate decisions must not set next_version")
        return self


class IngestionItemStatus(StrEnum):
    """Terminal processing status for one connector item."""

    STORED = "stored"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class IngestionItemResult(ContractModel):
    """Auditable terminal outcome for one source item."""

    external_id: NonEmptyStr = Field(description="Source-system item identifier.")
    status: IngestionItemStatus = Field(description="Terminal processing status.")
    raw_document_id: UUID | None = Field(
        default=None,
        description="Persisted raw-artifact identifier when raw storage succeeded.",
    )
    document_id: UUID | None = Field(
        default=None,
        description="Canonical or related stored document identifier when known.",
    )
    document_version: int | None = Field(
        default=None,
        ge=1,
        description="Canonical or related stored document version when known.",
    )
    decision: DocumentChangeDecision | None = Field(
        default=None,
        description="Incremental decision for stored or skipped content.",
    )
    validation_issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple,
        description="All deterministic validation findings for rejected content.",
    )
    error_code: str | None = Field(
        default=None,
        description="Stable application error code for transformation rejection.",
    )
    error_message: str | None = Field(
        default=None,
        description="Safe operator-facing transformation error message.",
    )

    @model_validator(mode="after")
    def validate_status_semantics(self) -> Self:
        """Keep status-specific result data internally consistent."""

        if self.status is IngestionItemStatus.STORED and (
            self.document_id is None or self.document_version is None
        ):
            raise ValueError("stored results require a document id and version")
        if self.status is IngestionItemStatus.REJECTED:
            if not self.validation_issues and self.error_code is None:
                raise ValueError("rejected results require validation issues or an error code")
        elif (
            self.validation_issues or self.error_code is not None or self.error_message is not None
        ):
            raise ValueError("only rejected results may contain rejection details")
        return self


class IngestionRunStatus(StrEnum):
    """Terminal status of a successfully completed connector stream."""

    COMPLETED = "completed"
    COMPLETED_WITH_REJECTIONS = "completed_with_rejections"


class IngestionRunResult(ContractModel):
    """Aggregate outcome returned after a connector stream and checkpoint commit."""

    connector_id: NonEmptyStr = Field(description="Connector that produced the run.")
    tenant_id: UUID = Field(description="Tenant processing boundary.")
    ceo_id: UUID = Field(description="Leader processing boundary.")
    status: IngestionRunStatus = Field(description="Successful terminal run status.")
    started_at: UtcDatetime = Field(description="UTC orchestration start timestamp.")
    completed_at: UtcDatetime = Field(description="UTC checkpoint completion timestamp.")
    items: tuple[IngestionItemResult, ...] = Field(
        default_factory=tuple,
        description="Ordered item-level outcomes.",
    )
    checkpoint: ConnectorCheckpoint = Field(description="Committed incremental progress.")
    stored_count: int = Field(ge=0, description="Number of canonical versions stored.")
    skipped_count: int = Field(ge=0, description="Number of unchanged or duplicate items skipped.")
    rejected_count: int = Field(ge=0, description="Number of malformed items rejected.")

    @model_validator(mode="after")
    def validate_aggregate_counts(self) -> Self:
        """Ensure aggregate fields exactly describe item-level outcomes."""

        expected_stored = sum(item.status is IngestionItemStatus.STORED for item in self.items)
        expected_skipped = sum(
            item.status in {IngestionItemStatus.UNCHANGED, IngestionItemStatus.DUPLICATE}
            for item in self.items
        )
        expected_rejected = sum(item.status is IngestionItemStatus.REJECTED for item in self.items)
        if (self.stored_count, self.skipped_count, self.rejected_count) != (
            expected_stored,
            expected_skipped,
            expected_rejected,
        ):
            raise ValueError("aggregate counts must match item statuses")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        expected_status = (
            IngestionRunStatus.COMPLETED_WITH_REJECTIONS
            if expected_rejected
            else IngestionRunStatus.COMPLETED
        )
        if self.status is not expected_status:
            raise ValueError("run status must reflect whether items were rejected")
        return self
