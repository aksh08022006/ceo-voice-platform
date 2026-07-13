"""Deterministic metadata extraction stage."""

import math
import re

from ceo_voice.ingestion.constants import (
    DEFAULT_READING_WORDS_PER_MINUTE,
    METADATA_SCHEMA_VERSION,
)
from ceo_voice.ingestion.contracts import ExtractedMetadata, IngestionDocument

_WORD_PATTERN = re.compile(r"\b[\w\u2019'-]+\b", flags=re.UNICODE)


class MetadataExtractor:
    """Calculate source-independent metadata without semantic inference."""

    def __init__(
        self,
        *,
        reading_words_per_minute: int = DEFAULT_READING_WORDS_PER_MINUTE,
        schema_version: str = METADATA_SCHEMA_VERSION,
    ) -> None:
        if reading_words_per_minute <= 0:
            raise ValueError("reading_words_per_minute must be positive")
        self._reading_words_per_minute = reading_words_per_minute
        self._schema_version = schema_version

    def extract(self, document: IngestionDocument) -> ExtractedMetadata:
        """Create an auditable metadata projection for one canonical document."""

        word_count = len(_WORD_PATTERN.findall(document.content))
        reading_seconds = math.ceil(word_count * 60 / self._reading_words_per_minute)
        return ExtractedMetadata(
            document_id=document.id,
            document_version=document.version,
            raw_document_id=document.raw_document_id,
            tenant_id=document.tenant_id,
            ceo_id=document.ceo_id,
            external_id=document.external_id,
            source=document.source,
            document_type=document.document_type,
            platform=document.platform,
            author=document.author,
            publication_date=document.publication_date,
            fetched_at=document.fetched_at,
            processed_at=document.processed_at,
            language=document.language,
            url=document.url,
            tags=document.tags,
            content_length_characters=len(document.content),
            content_length_bytes=len(document.content.encode("utf-8")),
            word_count=word_count,
            estimated_reading_time_seconds=reading_seconds,
            raw_checksum=document.raw_checksum,
            content_checksum=document.content_checksum,
            metadata_schema_version=self._schema_version,
        )
