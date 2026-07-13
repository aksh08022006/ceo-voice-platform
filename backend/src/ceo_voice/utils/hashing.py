"""Content-integrity hash helpers."""

from hashlib import sha256
from pathlib import Path

from ceo_voice.core.constants import DEFAULT_TEXT_ENCODING

_HASH_CHUNK_BYTES = 64 * 1024


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest of bytes."""

    return sha256(value).hexdigest()


def sha256_text(value: str, *, encoding: str = DEFAULT_TEXT_ENCODING) -> str:
    """Return the lowercase SHA-256 digest of encoded text."""

    return sha256_bytes(value.encode(encoding))


def sha256_file(path: Path) -> str:
    """Stream a file into a SHA-256 digest without loading it fully into memory."""

    digest = sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()
