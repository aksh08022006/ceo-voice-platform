"""Deterministic, NLP-library-independent structural document analysis."""

import re
from collections.abc import Iterable
from uuid import NAMESPACE_URL, UUID, uuid5

from ceo_voice.analysis.contracts import AddressedSpan, AnalyzedDocument
from ceo_voice.ingestion import CleanDocument
from ceo_voice.voice.enums import EvidenceUnitType
from ceo_voice.voice.primitives import SemanticVersion

_PARAGRAPH_PATTERN = re.compile(r"\S(?:.*?\S)?(?=\n[ \t]*\n|\Z)", re.DOTALL)
_SENTENCE_PATTERN = re.compile(r"\S.*?(?:[.!?]+(?=(?:[ \t]+[A-Z0-9#@])|\n|\Z)|\Z)", re.DOTALL)
_LINE_PATTERN = re.compile(r"[^\n]*\S[^\n]*")


class DeterministicDocumentAnalyzer:
    """Address document, paragraph, sentence, and line spans without linguistic inference.

    Sentence boundaries use an intentionally conservative punctuation rule. The versioned policy
    is replaceable later by a language-specific segmenter without changing analyzer contracts.
    """

    def __init__(self, *, segmentation_version: SemanticVersion) -> None:
        self._version = segmentation_version

    def analyze(self, document: CleanDocument) -> AnalyzedDocument:
        """Return a stable structural projection of one immutable document version."""

        document_span = self._span(
            document=document,
            unit_type=EvidenceUnitType.DOCUMENT,
            start=0,
            end=len(document.content),
            ordinal=0,
        )
        paragraphs = tuple(
            self._span(
                document=document,
                unit_type=EvidenceUnitType.PARAGRAPH,
                start=match.start(),
                end=match.end(),
                ordinal=ordinal,
            )
            for ordinal, match in enumerate(_PARAGRAPH_PATTERN.finditer(document.content))
        )
        sentences = tuple(self._sentences(document, paragraphs))
        lines = tuple(
            self._span(
                document=document,
                unit_type=EvidenceUnitType.WINDOW,
                start=match.start(),
                end=match.end(),
                ordinal=ordinal,
            )
            for ordinal, match in enumerate(_LINE_PATTERN.finditer(document.content))
        )
        return AnalyzedDocument(
            document=document,
            segmentation_version=self._version,
            document_span=document_span,
            paragraphs=paragraphs,
            sentences=sentences,
            lines=lines,
        )

    def _sentences(
        self, document: CleanDocument, paragraphs: tuple[AddressedSpan, ...]
    ) -> Iterable[AddressedSpan]:
        ordinal = 0
        for paragraph in paragraphs:
            paragraph_text = document.content[paragraph.start_offset : paragraph.end_offset]
            for match in _SENTENCE_PATTERN.finditer(paragraph_text):
                start = paragraph.start_offset + match.start()
                end = paragraph.start_offset + match.end()
                yield self._span(
                    document=document,
                    unit_type=EvidenceUnitType.SENTENCE,
                    start=start,
                    end=end,
                    ordinal=ordinal,
                    paragraph_id=paragraph.id,
                )
                ordinal += 1

    def _span(
        self,
        *,
        document: CleanDocument,
        unit_type: EvidenceUnitType,
        start: int,
        end: int,
        ordinal: int,
        paragraph_id: UUID | None = None,
    ) -> AddressedSpan:
        identity = uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    str(document.id),
                    str(document.version),
                    str(self._version),
                    unit_type.value,
                    str(start),
                    str(end),
                )
            ),
        )
        return AddressedSpan(
            id=identity,
            unit_type=unit_type,
            start_offset=start,
            end_offset=end,
            ordinal=ordinal,
            paragraph_id=identity if unit_type is EvidenceUnitType.PARAGRAPH else paragraph_id,
            sentence_id=identity if unit_type is EvidenceUnitType.SENTENCE else None,
        )
