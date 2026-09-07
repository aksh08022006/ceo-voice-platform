"""Conservative regression checks for unsupported outcome language, not semantic approval."""

import re

# These bounded cues target observed failures. They deliberately do not claim to exhaust claims
# or prove truth. An allowed phrase can still misattribute a fact or distort its scope.
_CUES = (
    r"\bstate.of.the.art\s+(?:results|performance|accuracy)\b",
    r"\b(?:we|I)\s+(?:(?:are|have|have been)\s+)?(?:seeing|seen|observed|measured|achieved|benchmarked)\b[^.!?\n]{0,80}",
    r"\b(?:real|measurable|proven)\s+(?:gains|improvements|savings|results)\b",
    r"\b(?:superior|better|improved|higher)\s+(?:performance|reliability|throughput|accuracy|quality)\b",
    r"\b(?:lower|reduced)\s+(?:costs?|latency)\b",
    r"\b(?:more\s+(?:capable,?\s+)?reliable|more\s+(?:unified\s+and\s+)?resilient)\b",
    r"\b(?:accelerate|improve|improves|improving|increase|increases)\s+(?:interoperability|portability|scalability|performance|reliability|throughput)\b",
    r"\b(?:work|works|working)\s+seamlessly\b",
    r"\b(?:all users|cannot match)\b",
    r"\b(?:outperforms?|outperformed)\b[^.!?\n]{0,80}",
    r"\b(?:best|better|improved)\s+(?:outcomes|results)\b",
    r"\b(?:accelerate|accelerates|accelerating)\s+(?:development|adoption|innovation)\b",
    r"\b(?:prevents?|eliminates?|removes?)\s+(?:vendor\s+)?(?:lock.in|friction)\b",
    r"\b(?:every|all)\s+(?:organizations?|customers?|developers?|applications?)\b",
    r"\breason\s+reliably\b",
    r"\bnew\s+failure\s+modes\b",
    r"\b(?:we|I)\s+(?:have\s+)?(?:always|long|consistently)\s+(?:believed|maintained|said|known|prioritized)\b",
    r"\b(?:accelerated|faster)\s+(?:development|adoption|innovation)\b",
    r"\b(?:drive|drives|driving)\s+compatibility\b",
    r"\b(?:better|more)\s+integrated\s+formats\b",
    r"\b(?:entire|whole)\s+(?:industry|ecosystem)\b",
)
_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _CUES)
_NEGATION = re.compile(r"\b(?:not|no|never|without|cannot|doesn't|don't|isn't)\b", re.IGNORECASE)
_TENTATIVE_BENEFIT = re.compile(
    r"\b(?:may|might|could)\s+(?:(?:potentially|possibly)\s+)?(?:help|improve|benefit)\b",
    re.IGNORECASE,
)
_STRONGER_BENEFIT = re.compile(
    r"\b(?:can|will|does|do)\s+(?:(?:certainly|definitely|clearly|reliably)\s+)?(?:help|improve|benefit)\b",
    re.IGNORECASE,
)


def unsupported_claim_cues(content: str, supplied_text: str) -> tuple[str, ...]:
    """Return exact novel positive-claim phrases for a bounded repair request.

    Nearby negation suppresses a cue so 'not better performance' is not treated as a promise.
    Exact lexical support is intentionally conservative: paraphrases can be flagged for review.
    """

    supplied = supplied_text.casefold()
    found: list[str] = []
    patterns = (
        (*_PATTERNS, _STRONGER_BENEFIT) if _TENTATIVE_BENEFIT.search(supplied_text) else _PATTERNS
    )
    for pattern in patterns:
        for match in pattern.finditer(content):
            phrase = match.group().strip()
            start = (
                max(content.rfind(".", 0, match.start()), content.rfind("\n", 0, match.start())) + 1
            )
            preceding = content[max(start, match.start() - 55) : match.start()]
            if (
                phrase.casefold() not in supplied
                and not _NEGATION.search(preceding)
                and phrase not in found
            ):
                found.append(phrase)
    return tuple(found)
