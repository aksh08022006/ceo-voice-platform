"""Tests for bounded, lawful local public-data export ingestion."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion import FetchRequest, LocalExportConnector, SourceItem
from ceo_voice.models import DocumentSourceType, Platform


def _request(
    tenant_id: UUID, *, path: str = "posts.json", cursor: str | None = None
) -> FetchRequest:
    return FetchRequest(
        tenant_id=tenant_id,
        ceo_id=UUID("22222222-2222-4222-8222-222222222222"),
        cursor=cursor,
        limit=10,
        options={"path": path},
    )


def test_local_export_maps_records_and_resumes(tmp_path: Path, tenant_id: UUID) -> None:
    (tmp_path / "posts.json").write_text(
        json.dumps(
            [
                {
                    "external_id": "post-1",
                    "content": "First post.",
                    "author": "Example Leader",
                    "publication_date": "2025-01-01T00:00:00Z",
                    "platform": "linkedin",
                },
                {
                    "external_id": "post-2",
                    "content": "Second post.",
                    "author": "Example Leader",
                    "publication_date": "2025-02-01T00:00:00Z",
                    "platform": "linkedin",
                    "metadata": {"source_collection": "official export"},
                },
            ]
        ),
        encoding="utf-8",
    )
    connector = LocalExportConnector(root=tmp_path, source_type=DocumentSourceType.LINKEDIN)

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(_request(tenant_id, cursor="1"))]

    items = asyncio.run(collect())

    assert len(items) == 1
    assert items[0].external_id == "post-2"
    assert items[0].platform is Platform.LINKEDIN
    assert items[0].cursor == "2"
    assert items[0].metadata["acquisition_method"] == "operator_provided_export"


def test_local_export_supports_jsonl_and_modified_after(tmp_path: Path, tenant_id: UUID) -> None:
    records = [
        {"external_id": "old", "content": "Old", "author": "Leader"},
        {
            "external_id": "new",
            "content": "New",
            "author": "Leader",
            "modified_at": "2025-02-01T00:00:00Z",
        },
    ]
    (tmp_path / "posts.jsonl").write_text(
        "\n".join(json.dumps(item) for item in records), encoding="utf-8"
    )
    connector = LocalExportConnector(root=tmp_path, source_type=DocumentSourceType.X)
    request = _request(tenant_id, path="posts.jsonl").model_copy(
        update={"modified_after": datetime(2025, 1, 1, tzinfo=UTC)}
    )

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(request)]

    items = asyncio.run(collect())

    assert [item.external_id for item in items] == ["new"]


@pytest.mark.parametrize(
    ("path", "cursor"),
    [("../outside.json", None), ("posts.txt", None), ("posts.json", "invalid")],
)
def test_local_export_rejects_unsafe_inputs(
    tmp_path: Path, tenant_id: UUID, path: str, cursor: str | None
) -> None:
    (tmp_path / "posts.json").write_text("[]", encoding="utf-8")
    connector = LocalExportConnector(root=tmp_path, source_type=DocumentSourceType.BLOG)

    async def collect() -> list[SourceItem]:
        return [
            item async for item in connector.fetch(_request(tenant_id, path=path, cursor=cursor))
        ]

    with pytest.raises(DataIngestionError):
        asyncio.run(collect())


def test_local_export_reports_invalid_payload(tmp_path: Path, tenant_id: UUID) -> None:
    (tmp_path / "posts.json").write_text('{"not": "a list"}', encoding="utf-8")
    connector = LocalExportConnector(root=tmp_path, source_type=DocumentSourceType.BLOG)

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(_request(tenant_id))]

    with pytest.raises(DataIngestionError, match="valid record collection"):
        asyncio.run(collect())
