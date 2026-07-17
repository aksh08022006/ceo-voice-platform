"""Local file connectors; these never access a network or browser session."""

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ceo_voice.acquisition.enums import AcquisitionMethod
from ceo_voice.collector.contracts import ConnectorCapabilities
from ceo_voice.utils.files import read_text_limited

_MAX_INPUT_BYTES = 250 * 1024 * 1024


class LocalImportConnector:
    """Read operator-provided JSON, JSONL, or CSV records exactly as supplied."""

    capabilities = ConnectorCapabilities(
        connector_name="local_import",
        supported_methods=(
            AcquisitionMethod.AUTHORIZED_EXPORT,
            AcquisitionMethod.MANUAL_CAPTURE,
        ),
    )

    def read(self, path: Path) -> Iterator[dict[str, Any]]:
        """Yield object rows from a bounded UTF-8 local file."""

        suffix = path.suffix.lower()
        text = read_text_limited(path, max_bytes=_MAX_INPUT_BYTES)
        if suffix == ".jsonl":
            for line in text.splitlines():
                if line.strip():
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError("JSONL rows must be objects")
                    yield item
            return
        if suffix == ".json":
            value = json.loads(text)
            rows = (
                value
                if isinstance(value, list)
                else value.get("records") if isinstance(value, dict) else None
            )
            if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
                raise ValueError("JSON input must be an object list or {records: [...]}")
            yield from rows
            return
        if suffix == ".csv":
            for row in csv.DictReader(io.StringIO(text)):
                yield {key: _decode_csv_value(value) for key, value in row.items()}
            return
        raise ValueError("supported input formats are .json, .jsonl, and .csv")


def _decode_csv_value(value: str | None) -> Any:
    """Decode JSON-valued CSV cells while leaving authored text untouched."""

    if value is None:
        return None
    if value in {"true", "false", "null"} or value.startswith(("{", "[")):
        return json.loads(value)
    return value
