"""Bounded encrypted editor snapshots bound to the authoritative database revision."""

import zlib
from uuid import UUID, uuid5

from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from ceo_voice.api.editor_schemas import EditorCursor, EditorState
from ceo_voice.generation.fidelity import validate_assessment
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.workspace.contracts import RevisionRecord, SnapshotWrite
from ceo_voice.workspace.errors import RevisionConflict


def revision_id(workflow_id: UUID, revision: int) -> UUID:
    return uuid5(workflow_id, f"editor-revision:{revision}")


class EditorStateCodec:
    """Retention has no browser TTL; only the server reads this authenticated ciphertext."""

    def __init__(self, key: str) -> None:
        self._cipher = Fernet(key.encode("ascii"))

    def seal(self, state: EditorState) -> SnapshotWrite:
        raw = state.model_dump_json().encode("utf-8")
        if len(raw) > 8_000_000:
            raise RevisionConflict("editor snapshot exceeds the storage limit")
        review = state.fidelity_review
        eligible = bool(
            state.format_valid
            and review
            and review.status == "clear"
            and review.candidate_sha256 == sha256_text(state.content)
            and state.review_run_id
        )
        return SnapshotWrite(
            encrypted_payload=self._cipher.encrypt(zlib.compress(raw)).decode("ascii"),
            candidate_sha256=sha256_text(state.content),
            review_run_id=state.review_run_id,
            review_eligible=eligible,
        )

    def seal_cursor(self, value: EditorCursor) -> str:
        return self._cipher.encrypt(value.model_dump_json().encode()).decode("ascii")

    def open_cursor(self, token: str) -> EditorCursor:
        try:
            if len(token) > 2_000:
                raise ValueError("oversize cursor")
            return EditorCursor.model_validate_json(self._cipher.decrypt(token, ttl=3_600))
        except (InvalidToken, ValueError, ValidationError) as exc:
            raise RevisionConflict(
                "Pagination expired or is invalid. Reload the first page."
            ) from exc

    def open(self, record: RevisionRecord) -> EditorState:
        try:
            compressed = self._cipher.decrypt(record.encrypted_payload)
            decoder = zlib.decompressobj()
            raw = decoder.decompress(compressed, 8_000_001)
            if len(raw) > 8_000_000 or not decoder.eof or decoder.unused_data:
                raise ValueError("invalid editor snapshot")
            state = EditorState.model_validate_json(raw)
            if (
                state.workspace_id,
                state.workflow_id,
                state.revision_number,
                sha256_text(state.content),
                state.review_run_id,
            ) != (
                record.workspace_id,
                record.workflow_id,
                record.revision,
                record.candidate_sha256,
                record.review_run_id,
            ):
                raise ValueError("editor snapshot revision binding mismatch")
            review = state.fidelity_review
            if review and review.assessment:
                by_id = {source.source_id: source for source in state.review_sources}
                if any(
                    source.source_id not in by_id
                    or sha256_text(by_id[source.source_id].text) != source.sha256
                    for source in review.sources
                ):
                    raise ValueError("stored review source binding mismatch")
                validate_assessment(
                    review.assessment, state.content, review.units, state.review_sources
                )
            eligible = bool(
                state.format_valid
                and review
                and review.status == "clear"
                and review.candidate_sha256 == record.candidate_sha256
                and state.review_run_id
            )
            if record.review_eligible != eligible:
                raise ValueError("editor review eligibility mismatch")
            return state
        except (InvalidToken, ValueError, zlib.error, ValidationError) as exc:
            raise RevisionConflict("stored editor revision could not be authenticated") from exc
