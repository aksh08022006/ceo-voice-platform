"""Tests for deterministic parsing and style-preserving cleaning."""

from datetime import datetime
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion import ContentParser, DocumentCleaner, SourceItem
from ceo_voice.models import ContentFormat, DocumentSourceType


def _source_item(
    *,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
    raw_content: bytes,
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT,
    encoding_hint: str | None = None,
) -> SourceItem:
    return SourceItem(
        external_id="source-1",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.BLOG,
        raw_content=raw_content,
        content_format=content_format,
        fetched_at=fixed_time,
        author="Example CEO",
        encoding_hint=encoding_hint,
    )


def test_parser_decodes_utf8_bom_without_changing_text(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"\xef\xbb\xbf  Keep spacing.  ",
    )

    parsed = ContentParser().parse(item)

    assert parsed.content == "  Keep spacing.  "
    assert parsed.encoding == "utf-8-sig"


def test_parser_honors_declared_encoding_and_rejects_bad_input(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    latin_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content="café".encode("latin-1"),
        encoding_hint="latin-1",
    )
    invalid_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"\xff",
    )
    unknown_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"content",
        encoding_hint="not-a-codec",
    )
    blank_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"  \n\t  ",
    )

    assert ContentParser().parse(latin_item).content == "café"
    with pytest.raises(DataIngestionError, match="decoded safely"):
        ContentParser().parse(invalid_item)
    with pytest.raises(DataIngestionError, match="decoded safely"):
        ContentParser().parse(unknown_item)
    with pytest.raises(DataIngestionError, match="is blank"):
        ContentParser().parse(blank_item)


def test_html_cleaning_removes_markup_and_unsafe_sections(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=(
            b"<article><p>  First <strong>move</strong>.  </p>"
            b"<script>steal()</script><p>Second &amp; final.</p></article>"
        ),
        content_format=ContentFormat.HTML,
    )

    cleaned = DocumentCleaner().clean(ContentParser().parse(item))

    assert cleaned.content == "  First move.  \n\nSecond & final."
    assert "steal" not in cleaned.content
    assert "html_to_text" in cleaned.applied_operations


def test_markdown_cleaning_removes_transport_syntax_but_keeps_list_shape(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    markdown = (
        "# A heading\n\n> **A bold point** with [evidence](https://example.com).\n\n"
        "- Keep this list marker\n\n`inline code`"
    )
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=markdown.encode(),
        content_format=ContentFormat.MARKDOWN,
    )

    cleaned = DocumentCleaner().clean(ContentParser().parse(item))

    assert cleaned.content.startswith("A heading\n\nA bold point with evidence.")
    assert "- Keep this list marker" in cleaned.content
    assert cleaned.content.endswith("inline code")
    assert "markdown_syntax_cleanup" in cleaned.applied_operations


def test_unicode_and_whitespace_cleanup_preserve_visible_style(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    text = "  Cafe\u0301\u00a0\x00🤝\u200d💼  \r\n   \r\nSecond  line.  "
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=text.encode(),
    )

    cleaned = DocumentCleaner().clean(ContentParser().parse(item))

    assert cleaned.content == "  Café 🤝\u200d💼  \n\nSecond  line.  "
    assert cleaned.content.startswith("  ")
    assert cleaned.content.endswith("  ")
    assert "unicode_nfc" in cleaned.applied_operations
    assert "unsafe_control_cleanup" in cleaned.applied_operations
    assert "transport_whitespace_cleanup" in cleaned.applied_operations


def test_only_consecutive_long_exact_duplicate_paragraphs_are_removed(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    long_paragraph = (
        "This duplicated transport paragraph is intentionally longer than eighty characters. "
    )
    long_paragraph += "It should appear once."
    content = (
        f"Again.\n\nAgain.\n\n{long_paragraph}\n\n{long_paragraph}\n\n"
        f"A different paragraph.\n\n{long_paragraph}"
    )
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=content.encode(),
    )

    cleaned = DocumentCleaner().clean(ContentParser().parse(item))

    assert cleaned.content.count("Again.") == 2
    assert cleaned.content.count(long_paragraph) == 2
    assert "consecutive_duplicate_paragraph_cleanup" in cleaned.applied_operations


def test_cleaner_rejects_invalid_deduplication_threshold() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        DocumentCleaner(duplicate_paragraph_min_chars=0)


def test_cleaner_rejects_markup_without_visible_content(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"<script>only hidden content</script>",
        content_format=ContentFormat.HTML,
    )

    with pytest.raises(DataIngestionError, match="removed all visible"):
        DocumentCleaner().clean(ContentParser().parse(item))
