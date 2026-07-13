"""Tests for connector discovery and source-family extensibility."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.ingestion import (
    ConnectorCapabilities,
    ConnectorRegistry,
    FetchRequest,
    SourceItem,
)
from ceo_voice.models import DocumentSourceType


class EmptyConnector:
    """Configurable connector used to test registry behavior."""

    capabilities = ConnectorCapabilities(
        supports_cursor=True,
        supports_modified_after=True,
    )

    def __init__(self, connector_id: str, source_type: DocumentSourceType) -> None:
        self.connector_id = connector_id
        self.source_type = source_type

    async def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        del request
        items: tuple[SourceItem, ...] = ()
        for item in items:
            yield item


def test_registry_resolves_connectors_without_source_branching() -> None:
    linkedin = EmptyConnector("linkedin-export", DocumentSourceType.LINKEDIN)
    api = EmptyConnector("linkedin-api", DocumentSourceType.LINKEDIN)
    youtube = EmptyConnector("youtube-transcript", DocumentSourceType.YOUTUBE)
    registry = ConnectorRegistry((linkedin, api, youtube))

    assert registry.get("linkedin-export") is linkedin
    assert registry.for_source(DocumentSourceType.LINKEDIN) == (linkedin, api)
    assert registry.registered_ids == (
        "linkedin-export",
        "linkedin-api",
        "youtube-transcript",
    )
    assert registry.supported_sources == {
        DocumentSourceType.LINKEDIN,
        DocumentSourceType.YOUTUBE,
    }


@pytest.mark.parametrize("connector_id", ["", "   "])
def test_registry_rejects_blank_connector_ids(connector_id: str) -> None:
    with pytest.raises(ConfigurationError, match="must not be blank"):
        ConnectorRegistry((EmptyConnector(connector_id, DocumentSourceType.X),))


def test_registry_rejects_duplicates_and_unknown_lookups() -> None:
    registry = ConnectorRegistry((EmptyConnector("same", DocumentSourceType.X),))

    with pytest.raises(ConfigurationError, match="already registered"):
        registry.register(EmptyConnector("same", DocumentSourceType.BLOG))
    with pytest.raises(ConfigurationError, match="not registered"):
        registry.get("unknown")


def test_connector_protocol_remains_tenant_agnostic(
    tenant_id: UUID,
) -> None:
    """Registry construction does not capture tenant state or credentials."""

    del tenant_id
    registry = ConnectorRegistry()

    assert registry.registered_ids == ()
    assert registry.supported_sources == frozenset()
