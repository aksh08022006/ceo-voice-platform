"""Deterministic, platform-isolated expression observations from admitted authored text."""

import re
from collections import Counter

from ceo_voice.models.enums import Platform
from ceo_voice.models.expression import ExpressionExample, ExpressionProfile
from ceo_voice.profiles import CuratedCorpus
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.voice.enums import SourceModality

# Visible symbol sequences, including ZWJ families, skin tones, flags and keycaps.
# This bounded detector is not an emoji-to-emotion classifier or full Unicode validation.
_BASE = r"[\U0001f300-\U0001faff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u3030\u303d\u3297\u3299]"
_PART = _BASE + r"[\ufe0e\ufe0f]?[\U0001f3fb-\U0001f3ff]?"
_EMOJI = re.compile(
    r"[0-9#*]\ufe0f?\u20e3|[\U0001f1e6-\U0001f1ff]{2}|[\u00a9\u00ae\u2122]\ufe0f|"
    + _PART
    + r"(?:\u200d"
    + _PART
    + r")*"
)
_CUES = {
    "enthusiasm": r"\b(?:excited|exciting|thrilled|delighted|proud)\b",
    "gratitude_credit": r"\b(?:thanks?|grateful|congratulations|congrats|credit|team)\b",
    "reflection": r"\b(?:learned|remember|looking back|lesson|years ago)\b",
    "curiosity": r"\b(?:curious|wonder|interesting|question)\b",
    "concern": r"\b(?:concerned|worry|risk|challenge|disappointed)\b",
    "qualification": r"\b(?:may|might|perhaps|depends|uncertain|in some cases)\b",
    "expressed_position": r"\b(?:I believe|we believe|I think|we think|in my view|should|must|open.source)\b",
}
_PATTERNS = {key: re.compile(pattern, re.IGNORECASE) for key, pattern in _CUES.items()}


def emoji_sequences(text: str) -> tuple[str, ...]:
    """Return visible symbol sequences without treating ASCII digits as emoji."""

    return tuple(match.group() for match in _EMOJI.finditer(text))


def build_expression_profile(corpus: CuratedCorpus, platform: Platform) -> ExpressionProfile:
    """Measure one person's same-platform authored documents, with exact source spans.

    Deduplication is exact-text only. Counts are descriptive, with no calibrated semantic score.
    Spoken and off-platform sources never establish this platform's emoji or emotional habits.
    """

    seen: set[str] = set()
    counts: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    candidates: list[ExpressionExample] = []
    hashes: list[str] = []
    emoji_documents = 0
    for item in sorted(corpus.documents, key=lambda item: str(item.document.id)):
        doc = item.document
        if item.source_modality is not SourceModality.AUTHORED_WRITTEN or doc.platform != platform:
            continue
        digest = sha256_text(doc.content)
        if digest in seen:
            continue
        seen.add(digest)
        hashes.append(f"{doc.id}:{doc.version}:{digest}")
        emojis = emoji_sequences(doc.content)
        emoji_documents += bool(emojis)
        symbols.update(sorted(set(emojis)))
        matches = [(key, pattern.search(doc.content)) for key, pattern in _PATTERNS.items()]
        labels = tuple(key for key, match in matches if match)
        counts.update(labels)
        if labels or emojis:
            # Prefer complete short posts. Longer excerpts start at a paragraph boundary and
            # end at a sentence/word boundary; never feed fragments cut through a word.
            first = min((match.start() for _, match in matches if match), default=0)
            start = max(0, doc.content.rfind("\n", 0, first) + 1)
            if len(doc.content) <= 900:
                start, end = 0, len(doc.content)
            else:
                end = min(len(doc.content), start + 900)
                if end < len(doc.content):
                    boundary = max(
                        doc.content.rfind(". ", start, end), doc.content.rfind("\n", start, end)
                    )
                    end = boundary + 1 if boundary > start else doc.content.rfind(" ", start, end)
                    if end <= start:
                        end = min(len(doc.content), start + 900)
            candidates.append(
                ExpressionExample(
                    document_id=doc.id,
                    source_url=str(doc.url) if doc.url else None,
                    start=start,
                    end=end,
                    text=doc.content[start:end],
                    complete_document=start == 0 and end == len(doc.content),
                    cues=tuple(
                        key
                        for key, pattern in _PATTERNS.items()
                        if pattern.search(doc.content[start:end])
                    )
                    + (("emoji_present",) if emoji_sequences(doc.content[start:end]) else ()),
                )
            )
    # Cover different visible cues before adding redundant examples; never rank by job title.
    selected: list[ExpressionExample] = []
    covered: set[str] = set()
    while candidates and len(selected) < 6:
        best = max(candidates, key=lambda item: len(set(item.cues) - covered))
        selected.append(best)
        covered.update(best.cues)
        candidates.remove(best)
    return ExpressionProfile(
        leader_id=corpus.identity.leader_id,
        platform=platform,
        corpus_hash=sha256_text("\n".join(hashes)),
        document_count=len(seen),
        documents_with_emoji=emoji_documents,
        emoji_inventory=tuple(symbol for symbol, _ in symbols.most_common(12)),
        cue_document_counts=dict(sorted(counts.items())),
        examples=tuple(selected),
    )
