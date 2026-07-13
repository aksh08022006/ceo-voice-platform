"""Source connector port used by ingestion orchestration."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ceo_voice.ingestion.contracts import ConnectorCapabilities, FetchRequest, SourceItem
from ceo_voice.models.base import NonEmptyStr
from ceo_voice.models.enums import DocumentSourceType


@runtime_checkable
class SourceConnector(Protocol):
    """Port implemented by every upload, export, API, or transcript source adapter.

    Connectors own authentication, pagination, rate limits, and provider payload translation. They
    yield provider-neutral `SourceItem` envelopes and never perform cleaning or persistence.
    """

    @property
    def connector_id(self) -> NonEmptyStr:
        """Return the stable identifier used for configuration and checkpointing."""

        ...

    @property
    def source_type(self) -> DocumentSourceType:
        """Return the source family emitted by this connector."""

        ...

    @property
    def capabilities(self) -> ConnectorCapabilities:
        """Describe incremental-fetch behavior without source-specific branching."""

        ...

    def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        """Yield at most `request.limit` raw items using connector-native backpressure."""

        ...
