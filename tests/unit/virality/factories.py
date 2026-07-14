"""Deterministic multi-leader fixtures for structural intelligence tests."""

from datetime import timedelta
from uuid import UUID

from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.enums import Platform
from ceo_voice.virality import (
    MetricCollectionMethod,
    PerformanceMetrics,
    Version,
    ViralityCorpus,
    ViralityCorpusItem,
)
from tests.unit.analysis.factories import NOW, TENANT_ID, clean_document

LIBRARY_ID = UUID(int=3101)


def document(
    number: int,
    *,
    leader: int | None = None,
    content: str | None = None,
    platform: Platform = Platform.LINKEDIN,
    thread_length: int = 1,
) -> CleanDocument:
    """Return a unique social post with a stable source fingerprint."""

    text = content or (
        "Why do strong teams ship consistently?\n\n"
        "The problem is unclear ownership.\n\n"
        "The solution is to make one person accountable.\n\n"
        "What would you change?"
    )
    base = clean_document(
        content=text,
        metadata={"thread_length": thread_length},
        platform=platform,
    )
    digit = format(number % 16, "x")
    return base.model_copy(
        update={
            "id": UUID(int=3200 + number),
            "raw_document_id": UUID(int=3300 + number),
            "ceo_id": UUID(int=3400 + (leader if leader is not None else number % 2)),
            "external_id": f"performance-post-{number}",
            "raw_checksum": digit * 64,
            "source_fingerprint": format((number + 1) % 16, "x") * 64,
            "content_checksum": format((number + 2) % 16, "x") * 64,
            "document_fingerprint": format((number + 3) % 16, "x") * 64,
            "publication_date": NOW + timedelta(days=number),
            "processed_at": NOW + timedelta(days=number),
        }
    )


def performance(number: int, *, impressions: int | None = 1_000) -> PerformanceMetrics:
    """Return an outcome snapshot with a controllable denominator."""

    return PerformanceMetrics(
        reactions=10 + number,
        comments=2,
        shares=1,
        saves=1,
        clicks=3,
        impressions=impressions,
        audience_size=5_000,
        collected_at=NOW + timedelta(days=40),
        method=MetricCollectionMethod.AUTHORIZED_EXPORT,
    )


def corpus(
    *numbers: int,
    corpus_number: int = 1,
    contents: tuple[str | None, ...] | None = None,
    impressions: tuple[int | None, ...] | None = None,
) -> ViralityCorpus:
    """Return a versioned authorized corpus spanning two leaders."""

    selected_contents = contents or (None,) * len(numbers)
    selected_impressions = impressions or (1_000,) * len(numbers)
    return ViralityCorpus(
        id=UUID(int=3500 + corpus_number),
        tenant_id=TENANT_ID,
        library_id=LIBRARY_ID,
        dataset_version=Version(major=1, minor=corpus_number - 1, patch=0),
        label=f"CEO structural benchmark {corpus_number}",
        items=tuple(
            ViralityCorpusItem(
                document=document(number, content=content),
                performance=performance(number, impressions=denominator),
            )
            for number, content, denominator in zip(
                numbers, selected_contents, selected_impressions, strict=True
            )
        ),
        created_at=NOW + timedelta(days=50 + corpus_number),
    )
