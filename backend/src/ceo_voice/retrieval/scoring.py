"""Transparent deterministic evidence scoring without semantic search."""

import re
from collections.abc import Iterable

from ceo_voice.context import GenerationIntent
from ceo_voice.retrieval.contracts import RetrievalScore

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_WEIGHTS = {
    "confidence": 0.24,
    "coverage": 0.14,
    "freshness": 0.10,
    "platform_match": 0.14,
    "feature_importance": 0.12,
    "representativeness": 0.14,
    "profile_authority": 0.08,
    "intent_match": 0.04,
}


def exact_intent_match(content: str, intent: GenerationIntent) -> float:
    """Score normalized exact-token overlap; this is lexical, not semantic retrieval."""

    intent_tokens = _tokens(f"{intent.topic} {intent.objective} {intent.audience}")
    if not intent_tokens:
        return 0.5
    content_tokens = _tokens(content)
    overlap = len(intent_tokens & content_tokens)
    return round(min(1.0, overlap / max(1, min(len(intent_tokens), 8))), 6)


def score_evidence(
    *,
    confidence: float,
    coverage: float,
    freshness: float,
    platform_match: float,
    feature_importance: float,
    representativeness: float,
    profile_authority: float,
    intent_match: float,
) -> RetrievalScore:
    """Combine named bounded factors using a reviewed fixed weight contract."""

    factors = {
        "confidence": confidence,
        "coverage": coverage,
        "freshness": freshness,
        "platform_match": platform_match,
        "feature_importance": feature_importance,
        "representativeness": representativeness,
        "profile_authority": profile_authority,
        "intent_match": intent_match,
    }
    base = round(sum(factors[name] * weight for name, weight in _WEIGHTS.items()), 6)
    return RetrievalScore(
        **factors,
        base_score=base,
        diversity_adjustment=0,
        final_score=base,
    )


def mean(values: Iterable[float], *, default: float = 0.5) -> float:
    """Return a bounded deterministic mean for evidence-weight components."""

    selected = tuple(values)
    return round(sum(selected) / len(selected), 6) if selected else default


def _tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(value)}
