"""Reusable style-preserving content cleaning stage."""

import re
import unicodedata
from collections.abc import Callable
from html.parser import HTMLParser

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion.constants import (
    CLEANER_VERSION,
    MIN_DEDUPLICATED_PARAGRAPH_CHARACTERS,
)
from ceo_voice.ingestion.contracts import CleanedContent, ParsedContent
from ceo_voice.models.enums import ContentFormat
from ceo_voice.utils.text import normalize_line_endings

_MARKDOWN_FENCE_PATTERN = re.compile(r"(?m)^\s*```[^\n]*\n?|^\s*~~~[^\n]*\n?")
_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^ {0,3}#{1,6}[\t ]+")
_MARKDOWN_QUOTE_PATTERN = re.compile(r"(?m)^ {0,3}>[\t ]?")
_MARKDOWN_LINK_PATTERN = re.compile(r"!?\[([^\]]+)]\([^\n)]+\)")
_MARKDOWN_INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
_MARKDOWN_STRONG_PATTERN = re.compile(r"(?:\*\*|__)(\S(?:.*?\S)?)(?:\*\*|__)")
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(?<!\w)(?:\*|_)(\S(?:.*?\S)?)(?:\*|_)(?!\w)")
_BLANK_LINE_RUN_PATTERN = re.compile(r"\n{3,}")
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "tr",
    }
)
_IGNORED_TAGS = frozenset({"script", "style", "template"})
_SINGLE_LINE_TAGS = frozenset({"br", "li", "tr"})


class _StylePreservingHTMLParser(HTMLParser):
    """Extract visible text while retaining block boundaries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth == 0 and tag in _BLOCK_TAGS:
            self._append_boundary(1 if tag in _SINGLE_LINE_TAGS else 2)

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth == 0 and tag in _BLOCK_TAGS:
            self._append_boundary(1 if tag in _SINGLE_LINE_TAGS else 2)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if not data.strip() and ("\n" in data or "\r" in data):
            return
        self._parts.append(data)

    def text(self) -> str:
        """Return extracted text without tag-generated outer newlines."""

        return "".join(self._parts).strip("\n")

    def _append_boundary(self, line_breaks: int) -> None:
        if not self._parts:
            return
        current = "".join(self._parts[-2:])
        existing = len(current) - len(current.rstrip("\n"))
        if existing < line_breaks:
            self._parts.append("\n" * (line_breaks - existing))


class DocumentCleaner:
    """Apply conservative transport cleanup while retaining voice-significant form."""

    def __init__(
        self,
        *,
        version: str = CLEANER_VERSION,
        duplicate_paragraph_min_chars: int = MIN_DEDUPLICATED_PARAGRAPH_CHARACTERS,
    ) -> None:
        if duplicate_paragraph_min_chars < 1:
            raise ValueError("duplicate_paragraph_min_chars must be positive")
        self._version = version
        self._duplicate_paragraph_min_chars = duplicate_paragraph_min_chars

    def clean(self, parsed: ParsedContent) -> CleanedContent:
        """Clean parsed content and record only operations that changed it."""

        content = parsed.content
        applied_operations: list[str] = []

        if parsed.content_format is ContentFormat.HTML:
            content = self._apply("html_to_text", content, _html_to_text, applied_operations)
        elif parsed.content_format is ContentFormat.MARKDOWN:
            content = self._apply(
                "markdown_syntax_cleanup", content, _clean_markdown, applied_operations
            )

        content = self._apply("unicode_nfc", content, _normalize_unicode, applied_operations)
        content = self._apply(
            "unsafe_control_cleanup", content, _remove_unsafe_controls, applied_operations
        )
        content = self._apply(
            "transport_whitespace_cleanup",
            content,
            _clean_transport_whitespace,
            applied_operations,
        )
        content = self._apply(
            "consecutive_duplicate_paragraph_cleanup",
            content,
            lambda value: _remove_consecutive_duplicate_paragraphs(
                value, min_chars=self._duplicate_paragraph_min_chars
            ),
            applied_operations,
        )

        if not content.strip():
            raise DataIngestionError("Cleaning removed all visible source content.")

        return CleanedContent(
            content=content,
            source_encoding=parsed.encoding,
            parser_version=parsed.parser_version,
            cleaner_version=self._version,
            applied_operations=tuple(applied_operations),
        )

    @staticmethod
    def _apply(
        name: str,
        content: str,
        operation: Callable[[str], str],
        applied_operations: list[str],
    ) -> str:
        cleaned = operation(content)
        if cleaned != content:
            applied_operations.append(name)
        return cleaned


def _html_to_text(value: str) -> str:
    parser = _StylePreservingHTMLParser()
    parser.feed(value)
    parser.close()
    return _BLANK_LINE_RUN_PATTERN.sub("\n\n", parser.text())


def _clean_markdown(value: str) -> str:
    value = _MARKDOWN_FENCE_PATTERN.sub("", value)
    value = _MARKDOWN_HEADING_PATTERN.sub("", value)
    value = _MARKDOWN_QUOTE_PATTERN.sub("", value)
    value = _MARKDOWN_LINK_PATTERN.sub(r"\1", value)
    value = _MARKDOWN_INLINE_CODE_PATTERN.sub(r"\1", value)
    value = _MARKDOWN_STRONG_PATTERN.sub(r"\1", value)
    return _MARKDOWN_EMPHASIS_PATTERN.sub(r"\1", value)


def _normalize_unicode(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\u00a0", " ").replace("\ufeff", "")


def _remove_unsafe_controls(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )


def _clean_transport_whitespace(value: str) -> str:
    normalized = normalize_line_endings(value)
    return "\n".join("" if line and not line.strip() else line for line in normalized.split("\n"))


def _remove_consecutive_duplicate_paragraphs(value: str, *, min_chars: int) -> str:
    parts: list[str] = re.split(r"(\n{2,})", value)
    output: list[str] = []
    previous_key: str | None = None

    for index in range(0, len(parts), 2):
        paragraph: str = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        key = paragraph.strip()
        if key == previous_key and len(key) >= min_chars:
            continue
        output.extend((paragraph, separator))
        if key:
            previous_key = key

    return "".join(output)
