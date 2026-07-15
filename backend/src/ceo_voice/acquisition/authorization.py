"""Per-item authorization gate between source connectors and ingestion."""

from collections.abc import AsyncIterator
from typing import NoReturn
from urllib.parse import urlsplit, urlunsplit

from ceo_voice.acquisition.contracts import (
    AuthorizedImportPolicy,
    AuthorizedImportReceipt,
    SourceCatalogEntry,
    SourceCatalogManifest,
)
from ceo_voice.acquisition.enums import (
    AuthorshipBasis,
    CorpusContentRole,
    ReusePermissionBasis,
    SourceReviewStatus,
)
from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion.connectors.base import SourceConnector
from ceo_voice.ingestion.contracts import ConnectorCapabilities, FetchRequest, SourceItem
from ceo_voice.models.enums import DocumentSourceType
from ceo_voice.utils.hashing import sha256_bytes

CATALOG_SOURCE_ID_KEY = "catalog_source_id"
AUTHORIZATION_RECEIPT_KEY = "authorization_receipt"


def _normalized_url(value: object) -> str:
    parts = urlsplit(str(value))
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


class CatalogItemAuthorizer:
    """Authorize one provider-neutral item against reviewed catalog metadata."""

    def __init__(
        self,
        manifest: SourceCatalogManifest,
        policy: AuthorizedImportPolicy | None = None,
    ) -> None:
        self._manifest = manifest
        self._policy = policy or AuthorizedImportPolicy()
        self._entries: dict[str, SourceCatalogEntry] = {}
        for entry in manifest.entries:
            if entry.source_id in self._entries:
                raise DataIngestionError(
                    "Source catalog contains duplicate identifiers.",
                    details={"source_id": entry.source_id},
                )
            self._entries[entry.source_id] = entry

    def authorize(self, item: SourceItem) -> SourceItem:
        """Return an item enriched with an immutable authorization receipt."""

        self._validate_scope(item)
        source_id_value = item.metadata.get(CATALOG_SOURCE_ID_KEY)
        if not isinstance(source_id_value, str) or not source_id_value.strip():
            self._reject("Source item does not reference a catalog entry.", item)
        source_id = source_id_value.strip()
        entry = self._entries.get(source_id)
        if entry is None:
            self._reject("Source item references an unknown catalog entry.", item, source_id)
        self._validate_entry(entry, item)
        content_sha256 = sha256_bytes(item.raw_content)
        if entry.content_fingerprint is not None and entry.content_fingerprint != content_sha256:
            self._reject(
                "Source content does not match the reviewed catalog fingerprint.", item, source_id
            )
        if self._policy.require_catalog_fingerprint and entry.content_fingerprint is None:
            self._reject("Catalog entry requires a reviewed content fingerprint.", item, source_id)

        receipt = AuthorizedImportReceipt(
            source_id=entry.source_id,
            catalog_schema_version=self._manifest.schema_version,
            acquisition_method=entry.acquisition_method,
            authorship_basis=entry.authorship_basis,
            content_role=entry.content_role,
            reuse_permission_basis=entry.reuse_permission_basis,
            content_sha256=content_sha256,
            reviewed_at=self._manifest.reviewed_at,
            reviewer_id=self._manifest.reviewer_id,
        )
        return item.model_copy(
            update={
                "metadata": {
                    **item.metadata,
                    AUTHORIZATION_RECEIPT_KEY: receipt.model_dump(mode="json"),
                }
            }
        )

    def validate_request(self, request: FetchRequest) -> None:
        """Reject cross-scope or unreviewed requests before invoking a source connector."""

        if (
            request.tenant_id != self._manifest.tenant_id
            or request.ceo_id != self._manifest.leader_id
        ):
            raise DataIngestionError("Fetch request is outside the catalog tenant or leader scope.")
        if self._policy.require_manifest_review and (
            self._manifest.reviewed_at is None or self._manifest.reviewer_id is None
        ):
            raise DataIngestionError("Source catalog has not completed human review.")

    def _validate_scope(self, item: SourceItem) -> None:
        if item.tenant_id != self._manifest.tenant_id or item.ceo_id != self._manifest.leader_id:
            self._reject("Source item is outside the catalog tenant or leader scope.", item)
        if self._policy.require_manifest_review and (
            self._manifest.reviewed_at is None or self._manifest.reviewer_id is None
        ):
            self._reject("Source catalog has not completed human review.", item)

    def _validate_entry(self, entry: SourceCatalogEntry, item: SourceItem) -> None:
        if entry.review_status is not SourceReviewStatus.APPROVED:
            self._reject("Catalog entry is not approved.", item, entry.source_id)
        if not entry.eligible_for_voice_analysis:
            self._reject("Catalog entry is not eligible for voice analysis.", item, entry.source_id)
        if entry.requires_authentication or entry.requires_payment:
            self._reject(
                "Catalog entry crosses a prohibited access boundary.", item, entry.source_id
            )
        if entry.authorship_basis is AuthorshipBasis.UNKNOWN:
            self._reject("Catalog entry has no supported authorship basis.", item, entry.source_id)
        if entry.reuse_permission_basis is ReusePermissionBasis.UNKNOWN:
            self._reject(
                "Catalog entry has no analytical reuse permission basis.",
                item,
                entry.source_id,
            )
        if entry.content_role is CorpusContentRole.FACTUAL_CONTEXT:
            self._reject("Factual context cannot enter the voice corpus.", item, entry.source_id)
        if item.source is not entry.source:
            self._reject(
                "Source item family does not match its catalog entry.", item, entry.source_id
            )
        if item.platform is not entry.platform:
            self._reject(
                "Source item platform does not match its catalog entry.", item, entry.source_id
            )
        if self._policy.require_author_match and (
            item.author is None
            or _normalized_name(item.author) != _normalized_name(self._manifest.leader_name)
        ):
            self._reject(
                "Source item author does not match the catalog leader.", item, entry.source_id
            )
        if self._policy.require_url_match and (
            item.url is None or _normalized_url(item.url) != _normalized_url(entry.canonical_url)
        ):
            self._reject("Source item URL does not match its catalog entry.", item, entry.source_id)
        if self._policy.require_publication_date_match and (
            item.publication_date is None
            or entry.publication_date is None
            or item.publication_date != entry.publication_date
        ):
            self._reject(
                "Source item publication date does not match its catalog entry.",
                item,
                entry.source_id,
            )

    @staticmethod
    def _reject(message: str, item: SourceItem, source_id: str | None = None) -> NoReturn:
        details = {"external_id": item.external_id}
        if source_id is not None:
            details["source_id"] = source_id
        raise DataIngestionError(message, details=details)


class CatalogAuthorizedConnector:
    """Connector decorator that fails closed before ingestion can persist an item."""

    def __init__(
        self,
        *,
        connector: SourceConnector,
        manifest: SourceCatalogManifest,
        policy: AuthorizedImportPolicy | None = None,
        connector_id: str | None = None,
    ) -> None:
        self._connector = connector
        self._authorizer = CatalogItemAuthorizer(manifest, policy)
        self.connector_id = connector_id or f"catalog-authorized-{connector.connector_id}"

    @property
    def source_type(self) -> DocumentSourceType:
        """Expose the decorated connector's source family."""

        return self._connector.source_type

    @property
    def capabilities(self) -> ConnectorCapabilities:
        """Preserve cursor and incremental capabilities of the decorated connector."""

        return self._connector.capabilities

    async def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        """Authorize each streamed item without buffering connector output."""

        self._authorizer.validate_request(request)
        async for item in self._connector.fetch(request):
            yield self._authorizer.authorize(item)
