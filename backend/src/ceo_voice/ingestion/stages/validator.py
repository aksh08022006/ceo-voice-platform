"""Non-short-circuiting source and canonical document validation."""

import re
from collections.abc import Callable
from datetime import datetime, timedelta

from ceo_voice.ingestion.constants import (
    DEFAULT_FUTURE_TIMESTAMP_TOLERANCE,
    DEFAULT_MAX_RAW_CONTENT_BYTES,
)
from ceo_voice.ingestion.contracts import (
    IngestionDocument,
    SourceItem,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from ceo_voice.utils.hashing import sha256_bytes, sha256_text
from ceo_voice.utils.time import utc_now

_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class SourceItemValidator:
    """Validate source envelope completeness before raw persistence and parsing."""

    def __init__(
        self,
        *,
        max_raw_bytes: int = DEFAULT_MAX_RAW_CONTENT_BYTES,
        future_tolerance: timedelta = DEFAULT_FUTURE_TIMESTAMP_TOLERANCE,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if max_raw_bytes < 1:
            raise ValueError("max_raw_bytes must be positive")
        if future_tolerance < timedelta(0):
            raise ValueError("future_tolerance must be non-negative")
        self._max_raw_bytes = max_raw_bytes
        self._future_tolerance = future_tolerance
        self._clock = clock

    def validate(self, item: SourceItem) -> ValidationResult:
        """Return all source-envelope issues in deterministic order."""

        issues: list[ValidationIssue] = []
        if item.author is None or not item.author.strip():
            issues.append(_error("missing_author", "A usable author is required.", "author"))
        if len(item.raw_content) > self._max_raw_bytes:
            issues.append(
                _error(
                    "raw_content_too_large",
                    f"Raw content exceeds {self._max_raw_bytes} bytes.",
                    "raw_content",
                )
            )
        if item.publication_date and item.publication_date > self._clock() + self._future_tolerance:
            issues.append(
                _error(
                    "future_publication_date",
                    "Publication date is implausibly far in the future.",
                    "publication_date",
                )
            )
        if item.language_hint and not _LANGUAGE_PATTERN.fullmatch(item.language_hint):
            issues.append(
                _error(
                    "malformed_language",
                    "Language hint must be a BCP 47-style code.",
                    "language_hint",
                )
            )
        return _result(issues)


class DocumentValidator:
    """Validate canonical content integrity and cross-stage timestamps."""

    def __init__(
        self,
        *,
        future_tolerance: timedelta = DEFAULT_FUTURE_TIMESTAMP_TOLERANCE,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if future_tolerance < timedelta(0):
            raise ValueError("future_tolerance must be non-negative")
        self._future_tolerance = future_tolerance
        self._clock = clock

    def validate(self, document: IngestionDocument) -> ValidationResult:
        """Return every integrity issue without mutating or discarding the document."""

        issues: list[ValidationIssue] = []
        if sha256_bytes(document.raw_content) != document.raw_checksum:
            issues.append(
                _error(
                    "raw_checksum_mismatch", "Raw content checksum does not match.", "raw_checksum"
                )
            )
        if sha256_text(document.content) != document.content_checksum:
            issues.append(
                _error(
                    "content_checksum_mismatch",
                    "Canonical content checksum does not match.",
                    "content_checksum",
                )
            )
        if document.processed_at < document.fetched_at:
            issues.append(
                _error(
                    "processing_before_fetch",
                    "Processing timestamp precedes acquisition.",
                    "processed_at",
                )
            )
        if (
            document.publication_date
            and document.publication_date > self._clock() + self._future_tolerance
        ):
            issues.append(
                _error(
                    "future_publication_date",
                    "Publication date is implausibly far in the future.",
                    "publication_date",
                )
            )
        if not _LANGUAGE_PATTERN.fullmatch(document.language):
            issues.append(
                _error(
                    "malformed_language",
                    "Language must be a BCP 47-style code.",
                    "language",
                )
            )
        if "\ufffd" in document.content:
            issues.append(
                _error(
                    "replacement_character",
                    "Canonical content contains a Unicode replacement character.",
                    "content",
                )
            )
        return _result(issues)


def _error(code: str, message: str, field: str) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity=ValidationSeverity.ERROR,
        field=field,
    )


def _result(issues: list[ValidationIssue]) -> ValidationResult:
    return ValidationResult(
        is_valid=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        issues=tuple(issues),
    )
