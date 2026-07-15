"""Catalog-authorized connector and ingestion-boundary tests."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ceo_voice.acquisition import (
    AUTHORIZATION_RECEIPT_KEY,
    CATALOG_SOURCE_ID_KEY,
    AcquisitionMethod,
    AuthorizedImportPolicy,
    AuthorshipBasis,
    CatalogAuthorizedConnector,
    CatalogItemAuthorizer,
    CorpusContentRole,
    ReusePermissionBasis,
    SourceCatalogEntry,
    SourceCatalogManifest,
    SourceReviewStatus,
    load_source_catalog,
)
from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion import (
    ConnectorRegistry,
    FetchRequest,
    IngestionPipeline,
    LocalExportConnector,
    SourceItem,
)
from ceo_voice.models import ContentFormat, DocumentSourceType, DocumentType, Platform
from ceo_voice.utils.hashing import sha256_bytes
from tests.unit.ingestion.pipeline_helpers import (
    AdvancingClock,
    FakeConnector,
    repositories,
    source_item,
)

TENANT_ID = UUID(int=1)
LEADER_ID = UUID(int=2)
REVIEWER_ID = UUID(int=3)
NOW = datetime(2026, 7, 15, tzinfo=UTC)
CONTENT = b"A reviewed source post."
URL = "https://example.com/posts/1"


def _entry(**updates: object) -> SourceCatalogEntry:
    values: dict[str, object] = {
        "source_id": "catalog-post-1",
        "source": DocumentSourceType.LINKEDIN,
        "platform": Platform.LINKEDIN,
        "document_type": DocumentType.SOCIAL_POST,
        "canonical_url": URL,
        "title": "Reviewed post",
        "publisher": "LinkedIn",
        "publication_date": NOW,
        "acquisition_method": AcquisitionMethod.AUTHORIZED_EXPORT,
        "review_status": SourceReviewStatus.APPROVED,
        "authorship_basis": AuthorshipBasis.FIRST_PARTY_ACCOUNT,
        "content_role": CorpusContentRole.PRIMARY_VOICE,
        "eligible_for_voice_analysis": True,
        "reuse_permission_basis": ReusePermissionBasis.ACCOUNT_AUTHORIZATION,
        "access_notes": "Account-authorized export.",
        "content_fingerprint": sha256_bytes(CONTENT),
        "captured_at": NOW,
    }
    values.update(updates)
    return SourceCatalogEntry.model_validate(values)


def _manifest(
    *entries: SourceCatalogEntry,
    reviewed: bool = True,
) -> SourceCatalogManifest:
    return SourceCatalogManifest(
        tenant_id=TENANT_ID,
        leader_id=LEADER_ID,
        leader_name="Example CEO",
        entries=entries or (_entry(),),
        created_at=NOW,
        reviewed_at=NOW if reviewed else None,
        reviewer_id=REVIEWER_ID if reviewed else None,
    )


def _item(**updates: object) -> SourceItem:
    item = source_item(
        tenant_id=TENANT_ID,
        ceo_id=LEADER_ID,
        fixed_time=NOW,
        external_id="provider-post-1",
        content=CONTENT,
    ).model_copy(
        update={
            "url": URL,
            "content_format": ContentFormat.PLAIN_TEXT,
            "metadata": {CATALOG_SOURCE_ID_KEY: "catalog-post-1"},
        }
    )
    return item.model_copy(update=updates)


def _request() -> FetchRequest:
    return FetchRequest(tenant_id=TENANT_ID, ceo_id=LEADER_ID, limit=10)


def test_authorizer_attaches_content_free_review_receipt() -> None:
    authorized = CatalogItemAuthorizer(_manifest()).authorize(_item())

    receipt = authorized.metadata[AUTHORIZATION_RECEIPT_KEY]
    assert isinstance(receipt, dict)
    assert receipt["source_id"] == "catalog-post-1"
    assert receipt["content_sha256"] == sha256_bytes(CONTENT)
    assert receipt["content_role"] == "primary_voice"
    assert receipt["reuse_permission_basis"] == "account_authorization"
    assert "raw_content" not in receipt


def test_connector_decorator_preserves_capabilities_and_streams_authorized_items() -> None:
    delegate = FakeConnector("export", DocumentSourceType.LINKEDIN, [_item()])
    connector = CatalogAuthorizedConnector(connector=delegate, manifest=_manifest())

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(_request())]

    items = asyncio.run(collect())

    assert connector.connector_id == "catalog-authorized-export"
    assert connector.source_type is DocumentSourceType.LINKEDIN
    assert connector.capabilities is delegate.capabilities
    assert len(items) == 1
    assert AUTHORIZATION_RECEIPT_KEY in items[0].metadata


@pytest.mark.parametrize(
    "fetch_request",
    (
        _request().model_copy(update={"tenant_id": UUID(int=99)}),
        _request().model_copy(update={"ceo_id": UUID(int=99)}),
    ),
)
def test_connector_rejects_cross_scope_request_before_invoking_delegate(
    fetch_request: FetchRequest,
) -> None:
    delegate = FakeConnector("export", DocumentSourceType.LINKEDIN, [_item()])
    connector = CatalogAuthorizedConnector(connector=delegate, manifest=_manifest())

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(fetch_request)]

    with pytest.raises(DataIngestionError, match="Fetch request is outside"):
        asyncio.run(collect())
    assert delegate.requests == []


def test_connector_rejects_unreviewed_manifest_before_invoking_delegate() -> None:
    delegate = FakeConnector("export", DocumentSourceType.LINKEDIN, [_item()])
    connector = CatalogAuthorizedConnector(connector=delegate, manifest=_manifest(reviewed=False))

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(_request())]

    with pytest.raises(DataIngestionError, match="human review"):
        asyncio.run(collect())
    assert delegate.requests == []


def test_committed_catalog_and_export_execute_the_authorized_import_contract() -> None:
    manifest = load_source_catalog(Path("data/examples/source-catalog.json"))
    delegate = LocalExportConnector(
        root=Path("data/examples"),
        source_type=DocumentSourceType.LINKEDIN,
    )
    connector = CatalogAuthorizedConnector(connector=delegate, manifest=manifest)
    request = FetchRequest(
        tenant_id=manifest.tenant_id,
        ceo_id=manifest.leader_id,
        limit=10,
        options={"path": "local-export.jsonl"},
    )

    async def collect() -> list[SourceItem]:
        return [item async for item in connector.fetch(request)]

    items = asyncio.run(collect())

    assert len(items) == 2
    assert all(AUTHORIZATION_RECEIPT_KEY in item.metadata for item in items)


@pytest.mark.parametrize(
    ("manifest", "item", "message"),
    (
        (_manifest(reviewed=False), _item(), "human review"),
        (_manifest(), _item(tenant_id=UUID(int=99)), "outside"),
        (_manifest(), _item(metadata={}), "does not reference"),
        (
            _manifest(),
            _item(metadata={CATALOG_SOURCE_ID_KEY: "missing"}),
            "unknown catalog",
        ),
        (_manifest(_entry(review_status=SourceReviewStatus.PENDING)), _item(), "not approved"),
        (_manifest(_entry(eligible_for_voice_analysis=False)), _item(), "not eligible"),
        (_manifest(_entry(requires_authentication=True)), _item(), "access boundary"),
        (_manifest(_entry(requires_payment=True)), _item(), "access boundary"),
        (_manifest(_entry(authorship_basis=AuthorshipBasis.UNKNOWN)), _item(), "authorship"),
        (
            _manifest(_entry(reuse_permission_basis=ReusePermissionBasis.UNKNOWN)),
            _item(),
            "reuse permission",
        ),
        (
            _manifest(_entry(content_role=CorpusContentRole.FACTUAL_CONTEXT)),
            _item(),
            "Factual context",
        ),
        (_manifest(_entry(source=DocumentSourceType.X)), _item(), "family"),
        (_manifest(_entry(platform=Platform.X)), _item(), "platform"),
        (_manifest(), _item(author="Another Person"), "author"),
        (_manifest(), _item(url="https://example.com/other"), "URL"),
        (
            _manifest(),
            _item(publication_date=datetime(2026, 7, 14, tzinfo=UTC)),
            "publication date",
        ),
        (_manifest(_entry(content_fingerprint="0" * 64)), _item(), "fingerprint"),
    ),
)
def test_authorizer_fails_closed_for_governance_mismatch(
    manifest: SourceCatalogManifest,
    item: SourceItem,
    message: str,
) -> None:
    with pytest.raises(DataIngestionError, match=message):
        CatalogItemAuthorizer(manifest).authorize(item)


def test_authorizer_rejects_duplicate_catalog_ids_and_required_missing_fingerprint() -> None:
    duplicate = _entry(canonical_url="https://example.com/posts/2")
    with pytest.raises(DataIngestionError, match="duplicate"):
        CatalogItemAuthorizer(_manifest(_entry(), duplicate))

    no_fingerprint = _entry(content_fingerprint=None, captured_at=None)
    with pytest.raises(DataIngestionError, match="requires a reviewed content fingerprint"):
        CatalogItemAuthorizer(
            _manifest(no_fingerprint),
            AuthorizedImportPolicy(require_catalog_fingerprint=True),
        ).authorize(_item())


def test_policy_can_relax_metadata_matching_for_reviewed_migration() -> None:
    policy = AuthorizedImportPolicy(
        require_manifest_review=False,
        require_author_match=False,
        require_url_match=False,
        require_publication_date_match=False,
    )
    item = _item(author=None, url=None, publication_date=None)

    authorized = CatalogItemAuthorizer(_manifest(reviewed=False), policy).authorize(item)

    assert AUTHORIZATION_RECEIPT_KEY in authorized.metadata


def test_authorized_connector_runs_through_existing_ingestion_pipeline() -> None:
    delegate = FakeConnector("export", DocumentSourceType.LINKEDIN, [_item()])
    connector = CatalogAuthorizedConnector(connector=delegate, manifest=_manifest())
    repository_bundle = repositories()
    pipeline = IngestionPipeline(
        connectors=ConnectorRegistry((connector,)),
        repositories=repository_bundle,
        clock=AdvancingClock(NOW),
    )

    result = asyncio.run(pipeline.run(connector.connector_id, _request()))
    stored = asyncio.run(
        repository_bundle.clean_documents.get_latest_by_source(
            TENANT_ID,
            LEADER_ID,
            DocumentSourceType.LINKEDIN,
            "provider-post-1",
        )
    )

    assert result.stored_count == 1
    assert stored is not None
    assert AUTHORIZATION_RECEIPT_KEY in stored.metadata
