"""Lawful, reproducible ingestion from operator-provided public-data exports."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

from pydantic import AnyUrl, Field, JsonValue, ValidationError, field_validator

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion.contracts import ConnectorCapabilities, FetchRequest, SourceItem
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import ContentFormat, DocumentSourceType, Platform
from ceo_voice.utils.files import ensure_path_within, read_text_limited
from ceo_voice.utils.time import utc_now

_MAX_EXPORT_BYTES = 50 * 1024 * 1024


class ExportRecord(ContractModel):
    """One normalized record in a JSON or JSONL export owned by the operator."""

    external_id: NonEmptyStr = Field(description="Stable source-system record identifier.")
    catalog_source_id: NonEmptyStr | None = Field(
        default=None,
        description="Reviewed source-catalog entry authorizing this record.",
    )
    content: NonBlankText = Field(description="Original post, article, or transcript text.")
    author: NonEmptyStr = Field(description="Author asserted by the export.")
    publication_date: UtcDatetime | None = None
    modified_at: UtcDatetime | None = None
    title: str | None = None
    language: str | None = None
    url: AnyUrl | None = None
    platform: Platform | None = None
    tags: tuple[NonEmptyStr, ...] = ()
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT
    source_version: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def protect_governance_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Prevent an export payload from forging authorization metadata."""

        reserved = {"catalog_source_id", "authorization_receipt"}
        if reserved.intersection(value):
            raise ValueError("metadata contains a reserved governance key")
        return value


class LocalExportConnector:
    """Read bounded JSON/JSONL exports without network access or platform scraping.

    The connector is rooted at a configured directory, so request options cannot traverse into
    arbitrary files. An integer cursor represents the next record index. Changed-since filtering
    uses the source modification timestamp when present and falls back to publication time.
    """

    capabilities = ConnectorCapabilities(
        supports_cursor=True,
        supports_modified_after=True,
        preserves_raw_bytes=False,
    )

    def __init__(
        self,
        *,
        root: Path,
        source_type: DocumentSourceType,
        connector_id: str | None = None,
        max_export_bytes: int = _MAX_EXPORT_BYTES,
    ) -> None:
        if max_export_bytes <= 0:
            raise ValueError("max_export_bytes must be positive")
        self._root = root.expanduser().resolve()
        self.source_type = source_type
        self.connector_id = connector_id or f"{source_type.value}-local-export"
        self._max_export_bytes = max_export_bytes

    async def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        """Yield validated records after the cursor, bounded by the request limit."""

        export_path = self._resolve_export_path(request)
        records = self._load_records(export_path)
        start = self._parse_cursor(request.cursor, len(records))
        yielded = 0
        fetched_at = utc_now()
        for index, record in enumerate(records[start:], start=start):
            effective_modified = record.modified_at or record.publication_date
            if request.modified_after is not None and (
                effective_modified is None or effective_modified <= request.modified_after
            ):
                continue
            if yielded >= request.limit:
                break
            yielded += 1
            yield SourceItem(
                external_id=record.external_id,
                tenant_id=request.tenant_id,
                ceo_id=request.ceo_id,
                source=self.source_type,
                raw_content=record.content.encode("utf-8"),
                content_format=record.content_format,
                fetched_at=fetched_at,
                author=record.author,
                platform=record.platform,
                publication_date=record.publication_date,
                source_modified_at=record.modified_at,
                title=record.title,
                language_hint=record.language,
                url=record.url,
                tags=record.tags,
                metadata={
                    **record.metadata,
                    "acquisition_method": "operator_provided_export",
                    "export_file": export_path.name,
                    **(
                        {"catalog_source_id": record.catalog_source_id}
                        if record.catalog_source_id is not None
                        else {}
                    ),
                },
                source_version=record.source_version,
                cursor=str(index + 1),
                encoding_hint="utf-8",
            )

    def _resolve_export_path(self, request: FetchRequest) -> Path:
        option = request.options.get("path")
        if not isinstance(option, str) or not option.strip():
            raise DataIngestionError(
                "Local export connector requires a non-empty 'path' option.",
                details={"connector_id": self.connector_id},
            )
        try:
            path = ensure_path_within(self._root / option, self._root)
        except ValueError as exc:
            raise DataIngestionError(
                "Export path is outside the configured data root.",
                details={"connector_id": self.connector_id},
            ) from exc
        if path.suffix.lower() not in {".json", ".jsonl"}:
            raise DataIngestionError("Export file must use .json or .jsonl.")
        return path

    def _load_records(self, path: Path) -> tuple[ExportRecord, ...]:
        try:
            content = read_text_limited(path, max_bytes=self._max_export_bytes)
            payloads = (
                [json.loads(line) for line in content.splitlines() if line.strip()]
                if path.suffix.lower() == ".jsonl"
                else json.loads(content)
            )
            if not isinstance(payloads, list):
                raise TypeError("top-level export value must be an array")
            return tuple(ExportRecord.model_validate(item) for item in payloads)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise DataIngestionError(
                "Export file could not be loaded as a valid record collection.",
                details={"path": path.name, "reason": type(exc).__name__},
            ) from exc

    def _parse_cursor(self, cursor: str | None, record_count: int) -> int:
        if cursor is None:
            return 0
        try:
            index = int(cursor)
        except ValueError as exc:
            raise DataIngestionError("Local export cursor must be an integer.") from exc
        if index < 0 or index > record_count:
            raise DataIngestionError("Local export cursor is outside the export bounds.")
        return index
