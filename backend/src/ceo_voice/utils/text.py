"""Conservative text helpers that preserve stylistic signal by default."""


def normalize_line_endings(text: str) -> str:
    """Convert CRLF and CR line endings to LF without changing other whitespace."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def remove_null_characters(text: str) -> str:
    """Remove null characters that commonly break storage and serialization layers."""

    return text.replace("\x00", "")


def is_blank(text: str) -> bool:
    """Return whether text contains no visible characters."""

    return not text.strip()


def truncate_text(text: str, max_chars: int, *, suffix: str = "…") -> str:
    """Limit text length while making truncation explicit.

    This helper is intended for logs and previews, never canonical source content.
    """

    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text
    if len(suffix) > max_chars:
        return suffix[:max_chars]
    return f"{text[: max_chars - len(suffix)]}{suffix}"
