"""Supported deterministic text measurements shared by evaluation dimensions."""

import re
import unicodedata
from collections.abc import Iterable
from statistics import fmean

_WORD = re.compile(r"\b\w+(?:['\N{RIGHT SINGLE QUOTATION MARK}.-]\w+)*\b", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?]+[.!?]?", re.MULTILINE)
_URL = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_HASHTAG = re.compile(r"(?<!\w)#[\w]+", re.UNICODE)
_MENTION = re.compile(r"(?<!\w)@[\w]+", re.UNICODE)
_LIST = re.compile(r"^[ \t]*(?:[-*+] |\d+[.)] )", re.MULTILINE)
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S", re.MULTILINE)
_REPEATED_WHITESPACE = re.compile(r"(?<!\n)[ \t]{2,}")
_NUMBER = re.compile(r"(?<!\w)(?:[$€£₹]\s*)?\d[\d,.]*(?:%|x|[kKmMbB])?(?!\w)")
_QUOTE = re.compile(r'(?:"[^"\n]+"|“[^”\n]+”)')
_CAPITALIZED = re.compile(r"\b[A-Z][\w.-]{2,}(?:\s+[A-Z][\w.-]+)*\b")
_EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2300, 0x23FF))


def words(text: str) -> tuple[str, ...]:
    return tuple(match.group() for match in _WORD.finditer(text))


def normalized_words(text: str) -> tuple[str, ...]:
    return tuple(item.casefold() for item in words(text))


def sentences(text: str) -> tuple[str, ...]:
    return tuple(
        match.group().strip() for match in _SENTENCE.finditer(text) if match.group().strip()
    )


def paragraphs(text: str) -> tuple[str, ...]:
    return tuple(item for item in re.split(r"\n\s*\n", text) if item.strip())


def style_measurements(text: str, *, thread_posts: int = 1) -> dict[str, float]:
    """Mirror the supported Tier-1 scalar feature semantics on a candidate string."""

    tokens = words(text)
    sentence_values = sentences(text)
    paragraph_values = paragraphs(text)
    sentence_lengths = tuple(len(words(item)) for item in sentence_values)
    paragraph_lengths = tuple(len(words(item)) for item in paragraph_values)
    cased = tuple(character for character in text if character.isalpha())
    cased_words = tuple(item for item in tokens if any(character.isalpha() for character in item))
    punctuation = sum(unicodedata.category(character).startswith("P") for character in text)
    emoji = sum(
        any(start <= ord(character) <= end for start, end in _EMOJI_RANGES) for character in text
    )
    return {
        "analysis.character-count": float(len(text)),
        "analysis.word-count": float(len(tokens)),
        "analysis.reading-time": len(tokens) * 60.0 / 200,
        "analysis.document-length": float(len(text)),
        "analysis.thread-length": float(thread_posts),
        "analysis.sentence-count": float(len(sentence_values)),
        "analysis.mean-sentence-words": fmean(sentence_lengths) if sentence_lengths else 0,
        "analysis.paragraph-count": float(len(paragraph_values)),
        "analysis.mean-paragraph-words": fmean(paragraph_lengths) if paragraph_lengths else 0,
        "analysis.line-break-count": float(text.count("\n")),
        "analysis.list-item-count": float(len(_LIST.findall(text))),
        "analysis.heading-count": float(len(_HEADING.findall(text))),
        "analysis.emoji-count": float(emoji),
        "analysis.punctuation-count": float(punctuation),
        "analysis.question-frequency": text.count("?") / max(1, len(sentence_values)),
        "analysis.exclamation-frequency": text.count("!") / max(1, len(sentence_values)),
        "analysis.link-count": float(len(_URL.findall(text))),
        "analysis.hashtag-count": float(len(_HASHTAG.findall(text))),
        "analysis.mention-count": float(len(_MENTION.findall(text))),
        "analysis.capitalization-ratio": (
            sum(character.isupper() for character in cased) / len(cased) if cased else 0
        ),
        "analysis.uppercase-word-ratio": (
            sum(item.isupper() for item in cased_words) / len(cased_words) if cased_words else 0
        ),
        "analysis.blank-line-count": float(len(re.findall(r"(?m)^[ \t]*$", text))),
        "analysis.repeated-whitespace-count": float(len(_REPEATED_WHITESPACE.findall(text))),
    }


def numeric_target(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        nested = value.get("value")
        if isinstance(nested, (int, float)) and not isinstance(nested, bool):
            return float(nested)
    return None


def proportional_similarity(actual: float, target: float) -> float:
    scale = max(abs(actual), abs(target), 1.0)
    return max(0.0, 1 - abs(actual - target) / scale)


def ngram_overlap(candidate: str, references: Iterable[str], *, size: int = 4) -> float:
    candidate_grams = _ngrams(normalized_words(candidate), size)
    if not candidate_grams:
        return 0
    reference_grams = set().union(*(_ngrams(normalized_words(item), size) for item in references))
    return len(candidate_grams & reference_grams) / len(candidate_grams)


def lexical_overlap(candidate: str, references: Iterable[str]) -> float:
    candidate_words = set(normalized_words(candidate))
    if not candidate_words:
        return 0
    reference_words = set().union(*(set(normalized_words(item)) for item in references))
    return len(candidate_words & reference_words) / len(candidate_words)


def factual_anchors(text: str) -> tuple[str, ...]:
    """Extract observable factual-risk anchors without claiming semantic fact checking."""

    names = []
    for match in _CAPITALIZED.finditer(text):
        prefix = text[: match.start()].rstrip()
        if " " in match.group() or (prefix and prefix[-1] not in ".!?\n"):
            names.append(match.group())
    anchors = {
        *(item.group() for item in _URL.finditer(text)),
        *(item.group() for item in _NUMBER.finditer(text)),
        *(item.group() for item in _QUOTE.finditer(text)),
        *names,
        *(item.group() for item in _HASHTAG.finditer(text)),
        *(item.group() for item in _MENTION.finditer(text)),
    }
    return tuple(sorted(anchors, key=str.casefold))


def _ngrams(tokens: tuple[str, ...], size: int) -> set[tuple[str, ...]]:
    return {tokens[index : index + size] for index in range(max(0, len(tokens) - size + 1))}
