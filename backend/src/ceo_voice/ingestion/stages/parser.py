"""Deterministic raw-byte decoding stage."""

import codecs

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion.constants import PARSER_VERSION
from ceo_voice.ingestion.contracts import ParsedContent, SourceItem


class ContentParser:
    """Decode connector bytes strictly without changing the resulting text."""

    def __init__(
        self, *, default_encoding: str = "utf-8-sig", version: str = PARSER_VERSION
    ) -> None:
        self._default_encoding = default_encoding
        self._version = version

    def parse(self, item: SourceItem) -> ParsedContent:
        """Decode one source item or raise a safe ingestion error."""

        requested_encoding = item.encoding_hint or self._default_encoding
        try:
            encoding = codecs.lookup(requested_encoding).name
            content = item.raw_content.decode(encoding, errors="strict")
        except (LookupError, UnicodeError) as exc:
            raise DataIngestionError(
                "Source content could not be decoded safely.",
                details={
                    "source": item.source.value,
                    "external_id": item.external_id,
                    "encoding": requested_encoding,
                },
            ) from exc

        if not content.strip():
            raise DataIngestionError(
                "Decoded source content is blank.",
                details={"source": item.source.value, "external_id": item.external_id},
            )

        return ParsedContent(
            content=content,
            encoding=encoding,
            content_format=item.content_format,
            parser_version=self._version,
        )
