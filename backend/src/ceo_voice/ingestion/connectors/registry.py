"""Connector discovery without source-specific orchestration branches."""

from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.ingestion.connectors.base import SourceConnector
from ceo_voice.models.enums import DocumentSourceType


class ConnectorRegistry:
    """Own connector registration and lookup by stable connector identifier."""

    def __init__(self, connectors: tuple[SourceConnector, ...] = ()) -> None:
        self._connectors: dict[str, SourceConnector] = {}
        for connector in connectors:
            self.register(connector)

    def register(self, connector: SourceConnector) -> None:
        """Register one connector, rejecting ambiguous identifiers."""

        connector_id = connector.connector_id.strip()
        if not connector_id:
            raise ConfigurationError("Connector identifiers must not be blank.")
        if connector_id in self._connectors:
            raise ConfigurationError(
                "Connector identifier is already registered.",
                details={"connector_id": connector_id},
            )
        self._connectors[connector_id] = connector

    def get(self, connector_id: str) -> SourceConnector:
        """Return a connector or fail with a configuration-level error."""

        try:
            return self._connectors[connector_id]
        except KeyError as exc:
            raise ConfigurationError(
                "Connector is not registered.",
                details={"connector_id": connector_id},
            ) from exc

    def for_source(self, source_type: DocumentSourceType) -> tuple[SourceConnector, ...]:
        """Return all configured connectors for a source family."""

        return tuple(
            connector
            for connector in self._connectors.values()
            if connector.source_type is source_type
        )

    @property
    def registered_ids(self) -> tuple[str, ...]:
        """Return connector identifiers in deterministic registration order."""

        return tuple(self._connectors)

    @property
    def supported_sources(self) -> frozenset[DocumentSourceType]:
        """Return source families backed by at least one configured connector."""

        return frozenset(connector.source_type for connector in self._connectors.values())
