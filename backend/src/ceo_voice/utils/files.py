"""Bounded, explicit filesystem helpers."""

from pathlib import Path

from ceo_voice.core.constants import DEFAULT_FILE_READ_LIMIT_BYTES, DEFAULT_TEXT_ENCODING


def ensure_path_within(path: Path, root: Path) -> Path:
    """Resolve a path and reject traversal outside an allowed root."""

    resolved_path = path.expanduser().resolve()
    resolved_root = root.expanduser().resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"path is outside the allowed root: {resolved_path}")
    return resolved_path


def read_text_limited(
    path: Path,
    *,
    encoding: str = DEFAULT_TEXT_ENCODING,
    max_bytes: int = DEFAULT_FILE_READ_LIMIT_BYTES,
) -> str:
    """Read a text file without allowing an unbounded memory allocation."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    with path.open("rb") as file_handle:
        content = file_handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"file exceeds the {max_bytes}-byte read limit: {path}")
    return content.decode(encoding)
