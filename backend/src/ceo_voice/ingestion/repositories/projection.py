"""Pure projection from transient pipeline documents to clean storage records."""

from ceo_voice.ingestion.contracts import CleanDocument, IngestionDocument


def to_clean_document(document: IngestionDocument) -> CleanDocument:
    """Remove raw bytes while retaining their immutable reference and checksums."""

    return CleanDocument(
        id=document.id,
        raw_document_id=document.raw_document_id,
        tenant_id=document.tenant_id,
        ceo_id=document.ceo_id,
        external_id=document.external_id,
        source=document.source,
        document_type=document.document_type,
        author=document.author,
        platform=document.platform,
        publication_date=document.publication_date,
        title=document.title,
        content=document.content,
        metadata=document.metadata,
        language=document.language,
        url=document.url,
        tags=document.tags,
        raw_checksum=document.raw_checksum,
        content_checksum=document.content_checksum,
        fetched_at=document.fetched_at,
        processed_at=document.processed_at,
        source_version=document.source_version,
        version=document.version,
    )
