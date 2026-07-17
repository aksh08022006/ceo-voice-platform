"""Filesystem orchestration for authorized local imports and resumability."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ceo_voice.acquisition.dataset import PublicContentRecord
from ceo_voice.collector.authorization import authorize
from ceo_voice.collector.connectors import LocalImportConnector
from ceo_voice.collector.contracts import (
    AcquisitionDecision,
    Checkpoint,
    CollectedVersion,
    CollectionReport,
    SourcePolicy,
)


class LocalFileStore:
    """Local development storage for canonical JSONL, receipts, and checkpoints."""

    def __init__(self, root: Path) -> None:
        """Create the ignored storage layout below ``root`` as needed."""

        self.root = root

    def _path(self, category: str, source_id: str, suffix: str) -> Path:
        """Return a contained content or metadata path for one source."""

        return self.root / category / f"{source_id}{suffix}"

    def write_receipt(self, receipt: Any) -> None:
        """Persist a content-free authorization receipt."""

        path = self._path("metadata/receipts", receipt.source_id, ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    def load_versions(self, source_id: str) -> dict[tuple[str, str], CollectedVersion]:
        """Load known content fingerprints without loading canonical content."""

        path = self._path("metadata/versions", source_id, ".json")
        if not path.exists():
            return {}
        values = json.loads(path.read_text(encoding="utf-8"))
        return {
            (item["platform"], item["source_post_id"]): CollectedVersion.model_validate(item)
            for item in values
        }

    def write_versions(
        self, source_id: str, versions: dict[tuple[str, str], CollectedVersion]
    ) -> None:
        """Atomically replace fingerprint metadata after a successful collection."""

        path = self._path("metadata/versions", source_id, ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps([value.model_dump(mode="json") for value in versions.values()])
        path.write_text(serialized, encoding="utf-8")

    def write_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Persist the last completed local import checkpoint."""

        path = self._path("metadata/checkpoints", checkpoint.source_id, ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")

    def append_records(self, source_id: str, records: list[PublicContentRecord]) -> Path:
        """Append immutable records to the source's canonical JSONL stream."""

        path = self._path("canonical", source_id, ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(record.model_dump_json() + "\n")
        return path

    def store_raw_payload(self, source_id: str, input_path: Path) -> Path:
        """Copy the original operator payload into ignored raw storage unchanged."""

        path = self.root / "raw" / source_id / input_path.name
        path.parent.mkdir(parents=True, exist_ok=True)
        with input_path.open("rb") as source, path.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        return path


class CollectorService:
    """Authorize and import local records without overwriting past content versions."""

    def __init__(
        self, store: LocalFileStore, connector: LocalImportConnector | None = None
    ) -> None:
        """Bind I/O dependencies for testable local collection."""

        self._store = store
        self._connector = connector or LocalImportConnector()

    def collect(self, policy: SourcePolicy, input_path: Path) -> CollectionReport:
        """Collect an approved local input, preserving edits as appended versions."""

        receipt = authorize(policy, self._connector.capabilities)
        self._store.write_receipt(receipt)
        if receipt.decision is AcquisitionDecision.BLOCK:
            return CollectionReport(
                source_id=policy.source_id,
                fetched=0,
                admitted=0,
                blocked=1,
                duplicates=0,
                unchanged=0,
                edited_versions=0,
            )
        self._store.store_raw_payload(policy.source_id, input_path)
        known = self._store.load_versions(policy.source_id)
        seen: set[tuple[str, str]] = set()
        pending: list[PublicContentRecord] = []
        fetched = duplicates = unchanged = edited = blocked = 0
        for row in self._connector.read(input_path):
            fetched += 1
            try:
                record = PublicContentRecord.model_validate(row)
            except ValidationError:
                blocked += 1
                continue
            key = (str(record.platform), record.source_post_id)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            previous = known.get(key)
            if previous is not None and previous.content_sha256 == record.content_sha256:
                unchanged += 1
                continue
            if previous is not None:
                edited += 1
                record = record.model_copy(
                    update={"record_id": f"{record.record_id}:v{previous.version + 1}"}
                )
                known[key] = CollectedVersion(
                    platform=key[0],
                    source_post_id=key[1],
                    content_sha256=record.content_sha256,
                    version=previous.version + 1,
                    observed_at=datetime.now(UTC),
                )
            else:
                known[key] = CollectedVersion(
                    platform=key[0],
                    source_post_id=key[1],
                    content_sha256=record.content_sha256,
                    version=1,
                    observed_at=datetime.now(UTC),
                )
            pending.append(record)
        output = self._store.append_records(policy.source_id, pending) if pending else None
        self._store.write_versions(policy.source_id, known)
        self._store.write_checkpoint(
            Checkpoint(
                source_id=policy.source_id,
                completed_at=datetime.now(UTC),
                records_seen=fetched,
                records_written=len(pending),
            )
        )
        return CollectionReport(
            source_id=policy.source_id,
            fetched=fetched,
            admitted=len(pending),
            blocked=blocked,
            duplicates=duplicates,
            unchanged=unchanged,
            edited_versions=edited,
            output_path=str(output) if output else None,
        )
