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
)
_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _CUES)
_NEGATION = re.compile(r"\b(?:not|no|never|without|cannot|doesn't|don't|isn't)\b", re.IGNORECASE)


def unsupported_claim_cues(content: str, supplied_text: str) -> tuple[str, ...]:
    """Return exact novel positive-claim phrases for a bounded repair request.

    Nearby negation suppresses a cue so 'not better performance' is not treated as a promise.
    Exact lexical support is intentionally conservative: paraphrases can be flagged for review.
    """

    supplied = supplied_text.casefold()
    found: list[str] = []
    for pattern in _PATTERNS:
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
