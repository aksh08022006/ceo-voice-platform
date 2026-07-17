"""Canonical handoff contract for operator-collected public social content."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, HttpUrl, ValidationError, model_validator

from ceo_voice.acquisition.enums import (
    AcquisitionMethod,
    AuthorshipBasis,
    ReusePermissionBasis,
)
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import ContentType, Platform
from ceo_voice.utils.files import read_text_limited
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.virality.enums import MetricCollectionMethod

_MAX_DATASET_BYTES = 250 * 1024 * 1024


class PublicPerformanceSnapshot(ContractModel):
    """One time-pinned, source-faithful engagement snapshot."""

    reactions: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    audience_size: int | None = Field(default=None, ge=0)
    collected_at: UtcDatetime
    method: MetricCollectionMethod

    @model_validator(mode="after")
    def require_observed_metric(self) -> Self:
        if all(
            item is None
            for item in (
                self.reactions,
                self.comments,
                self.shares,
                self.saves,
                self.clicks,
                self.impressions,
                self.audience_size,
            )
        ):
            raise ValueError("performance snapshot must contain an observed metric")
        return self


class PublicContentRecord(ContractModel):
    """One exact authored item emitted by an external collection process."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    record_id: NonEmptyStr
    leader_slug: NonEmptyStr
    leader_name: NonEmptyStr
    dataset_partition: Literal["profile", "held_out", "virality"]
    author_handle: NonEmptyStr
    platform: Platform
    content_type: ContentType = ContentType.POST
    source_post_id: NonEmptyStr
    canonical_url: HttpUrl
    content: NonBlankText
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    language: NonEmptyStr = "en"
    publication_date: UtcDatetime
    collected_at: UtcDatetime
    acquisition_method: AcquisitionMethod
    authorship_basis: AuthorshipBasis
    reuse_permission_basis: ReusePermissionBasis = ReusePermissionBasis.UNKNOWN
    terms_url: HttpUrl | None = None
    license_url: HttpUrl | None = None
    requires_authentication: bool
    requires_payment: bool
    is_repost: bool = False
    is_quote_post: bool = False
    quoted_content: str | None = None
    thread_id: str | None = None
    thread_position: int | None = Field(default=None, ge=1, le=100)
    thread_total: int | None = Field(default=None, ge=2, le=100)
    performance: PublicPerformanceSnapshot | None = None

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        """Reject lossy, internally inconsistent, or unsupported social records."""

        if self.platform not in {Platform.X, Platform.LINKEDIN}:
            raise ValueError("public social datasets support only X and LinkedIn")
        if sha256_text(self.content) != self.content_sha256:
            raise ValueError("content_sha256 does not match the exact content")
        thread_fields = (self.thread_id, self.thread_position, self.thread_total)
        if self.content_type is ContentType.THREAD:
            if self.platform is not Platform.X or any(item is None for item in thread_fields):
                raise ValueError("X thread records require id, position, and total")
            assert self.thread_position is not None and self.thread_total is not None
            if self.thread_position > self.thread_total:
                raise ValueError("thread position cannot exceed thread total")
        elif any(item is not None for item in thread_fields):
            raise ValueError("thread fields are allowed only for thread records")
        if self.is_quote_post != (self.quoted_content is not None):
            raise ValueError("quote-post status and quoted_content must agree")
        if self.collected_at < self.publication_date:
            raise ValueError("collection cannot predate publication")
        if self.performance is not None and self.performance.collected_at < self.publication_date:
            raise ValueError("performance snapshot cannot predate publication")
        return self


class DatasetValidationReport(ContractModel):
    """Content-free summary of one validated JSONL handoff."""

    valid: bool
    record_count: int = Field(ge=0)
    leader_count: int = Field(ge=0)
    platforms: tuple[Platform, ...]
    records_with_performance: int = Field(ge=0)
    reusable_records: int = Field(ge=0)
    blocked_records: int = Field(ge=0)
    errors: tuple[NonEmptyStr, ...]


def validate_public_dataset(path: Path) -> DatasetValidationReport:
    """Validate a bounded JSONL dataset without storing or logging its content."""

    try:
        text = read_text_limited(path, max_bytes=_MAX_DATASET_BYTES)
    except (OSError, UnicodeError, ValueError) as exc:
        return DatasetValidationReport(
            valid=False,
            record_count=0,
            leader_count=0,
            platforms=(),
            records_with_performance=0,
            reusable_records=0,
            blocked_records=0,
            errors=(f"dataset: {type(exc).__name__}",),
        )
    records: list[PublicContentRecord] = []
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(PublicContentRecord.model_validate_json(line))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            count = exc.error_count() if isinstance(exc, ValidationError) else 1
            errors.append(f"line {line_number}: invalid record ({count} error(s))")
    keys = [(item.platform, item.source_post_id) for item in records]
    duplicate_count = len(keys) - len(set(keys))
    if duplicate_count:
        errors.append(f"dataset: {duplicate_count} duplicate platform/post id(s)")
    reusable = sum(
        item.reuse_permission_basis is not ReusePermissionBasis.UNKNOWN
        and not item.requires_authentication
        and not item.requires_payment
        and not item.is_repost
        for item in records
    )
    return DatasetValidationReport(
        valid=bool(records) and not errors,
        record_count=len(records),
        leader_count=len({item.leader_slug for item in records}),
        platforms=tuple(sorted({item.platform for item in records}, key=str)),
        records_with_performance=sum(item.performance is not None for item in records),
        reusable_records=reusable,
        blocked_records=len(records) - reusable,
        errors=tuple(errors or (() if records else ("dataset: no records",))),
    )
