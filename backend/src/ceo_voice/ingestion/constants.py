"""Version identifiers and conservative defaults owned by ingestion."""

from datetime import timedelta

PARSER_VERSION = "text-parser-v1"
CLEANER_VERSION = "style-preserving-cleaner-v1"
METADATA_SCHEMA_VERSION = "document-metadata-v1"
DEFAULT_READING_WORDS_PER_MINUTE = 200
DEFAULT_MAX_RAW_CONTENT_BYTES = 10 * 1024 * 1024
DEFAULT_FUTURE_TIMESTAMP_TOLERANCE = timedelta(minutes=5)
MIN_DEDUPLICATED_PARAGRAPH_CHARACTERS = 80
