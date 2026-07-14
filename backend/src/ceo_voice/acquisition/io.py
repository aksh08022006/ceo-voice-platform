"""Bounded file adapters for acquisition manifests and audit reports."""

from pathlib import Path

from ceo_voice.acquisition.contracts import SourceCatalogManifest
from ceo_voice.utils.files import read_text_limited

MAX_CATALOG_BYTES = 5 * 1024 * 1024


def load_source_catalog(path: Path) -> SourceCatalogManifest:
    """Load and validate a bounded UTF-8 source catalog JSON file."""

    return SourceCatalogManifest.model_validate_json(
        read_text_limited(path, max_bytes=MAX_CATALOG_BYTES)
    )
