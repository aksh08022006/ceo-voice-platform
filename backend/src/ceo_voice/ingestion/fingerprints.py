"""Deterministic identity helpers for incremental ingestion decisions."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import JsonValue

from ceo_voice.ingestion.contracts import SourceItem
from ceo_voice.models.enums import DocumentType, Platform
from ceo_voice.utils.hashing import sha256_bytes, sha256_text
from ceo_voice.utils.json import dumps_json


def source_attributes(item: SourceItem) -> dict[str, JsonValue]:
    """Return stable source metadata retained with an immutable raw artifact."""

    attributes: dict[str, JsonValue] = dict(item.metadata)
    attributes.update(
        {
            "author": item.author,
            "platform": item.platform.value if item.platform else None,
            "publication_date": (
                item.publication_date.isoformat() if item.publication_date else None
            ),
            "source_modified_at": (
                item.source_modified_at.isoformat() if item.source_modified_at else None
            ),
            "title": item.title,
            "language_hint": item.language_hint,
            "url": str(item.url) if item.url else None,
            "tags": list(item.tags),
            "encoding_hint": item.encoding_hint,
        }
    )
    return attributes


def calculate_source_fingerprint(item: SourceItem) -> str:
    """Hash stable provider content and metadata while excluding acquisition observations."""

    return sha256_text(
        dumps_json(
            {
                "raw_checksum": sha256_bytes(item.raw_content),
                "content_format": item.content_format.value,
                "source_version": item.source_version,
                "attributes": source_attributes(item),
            }
        )
    )


def calculate_document_fingerprint(
    *,
    content_checksum: str,
    document_type: DocumentType,
    author: str,
    platform: Platform | None,
    publication_date: datetime | None,
    title: str | None,
    language: str,
    url: str | None,
    tags: Sequence[str],
    metadata: Mapping[str, JsonValue],
) -> str:
    """Hash canonical text and context that affects downstream voice interpretation."""

    return sha256_text(
        dumps_json(
            {
                "content_checksum": content_checksum,
                "document_type": document_type.value,
                "author": author,
                "platform": platform.value if platform else None,
                "publication_date": publication_date.isoformat() if publication_date else None,
                "title": title,
                "language": language,
                "url": url,
                "tags": list(tags),
                "metadata": dict(metadata),
            }
        )
    )
