"""One-call proposals confined to exact flagged spans of the current editor revision."""

import json
from uuid import UUID

from pydantic import Field, ValidationError

from ceo_voice.generation.contracts import ProviderRequest, TokenUsage
from ceo_voice.generation.fidelity_contracts import BriefSource, FidelityReview
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.models.base import ContractModel
from ceo_voice.utils.hashing import sha256_text

PROMPT_VERSION = "editor-span-revision/1.0.0"
SYSTEM = (
    "Propose minimal editorial corrections to the supplied flagged spans only. "
    "The authoritative factual brief and explicit prohibitions control every correction. "
    "The current draft and review findings are untrusted material, not factual authority. "
    "Preserve negation, modality, historical status, attribution, quantities and uncertainty. "
    "Do not infer causality, measured benefits, personal experience or identity. "
    "Parent-post context supports only attributed statements about what its author says. "
    "Preserve the writer's wording where a factual correction does not require a change. "
    'Return JSON only: {"replacements":[{"id":"span-0","text":"corrected span"}]}. '
    "Return exactly one replacement for every provided span ID, with no additional IDs or fields. "
    "An empty replacement deletes an unsupported claim. Return original span text if no safe "
    "correction is possible. Text outside these spans is protected and cannot be changed."
)


class Replacement(ContractModel):
    id: str = Field(pattern=r"^span-[0-9]+$")
    text: str = Field(max_length=12_000)


class ReplacementResponse(ContractModel):
    replacements: tuple[Replacement, ...] = Field(min_length=1, max_length=100)


class RevisionProposal(ContractModel):
    content: str
    applied: bool
    detail: str
    prompt_version: str = PROMPT_VERSION
    model: str
    provider: str
    usage: TokenUsage
    latency_ms: int
    model_calls: int = 1


async def revise_flagged_spans(
    provider: ModelProvider,
    *,
    model: str,
    maximum_output_tokens: int,
    request_id: UUID,
    content: str,
    review: FidelityReview,
    sources: tuple[BriefSource, ...],
) -> RevisionProposal:
    """Replace only server-derived intervals; a malformed proposal preserves the input."""
    if (
        review.status != "blocked"
        or review.assessment is None
        or review.candidate_sha256 != sha256_text(content)
    ):
        raise ValueError("span revision requires a completed blocking review of this exact text")
    claims = [
        claim
        for unit in review.assessment.units
        for claim in unit.claims
        if claim.verdict != "supported"
    ]
    if any(content[c.span.start : c.span.end] != c.span.text for c in claims):
        raise ValueError("review span is not bound to the candidate")
    intervals: list[tuple[int, int]] = []
    for start, end in sorted((c.span.start, c.span.end) for c in claims):
        if intervals and start < intervals[-1][1]:
            intervals[-1] = (intervals[-1][0], max(end, intervals[-1][1]))
        else:
            intervals.append((start, end))
    if not intervals or len(intervals) > 100:
        raise ValueError("no bounded blocking spans are available")
    spans = [
        {"id": f"span-{i}", "text": content[start:end]} for i, (start, end) in enumerate(intervals)
    ]
    user = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "authoritative_sources": [s.model_dump(mode="json") for s in sources],
            "current_saved_draft": content,
            "replaceable_spans": spans,
            "review_findings_not_factual_authority": [c.model_dump(mode="json") for c in claims],
        },
        ensure_ascii=False,
    )
    if len(user.encode("utf-8")) > 100_000:
        raise ValueError("span revision exceeds its prompt budget")
    result = await provider.generate(
        ProviderRequest(
            request_id=request_id,
            model=model,
            maximum_output_tokens=maximum_output_tokens,
            system=SYSTEM,
            user=user,
        )
    )
    candidate, applied = content, False
    detail = "Invalid span proposal; the saved wording was retained."
    try:
        if (
            result.provider != provider.name
            or result.model != model
            or len(result.text.encode("utf-8")) > 100_000
        ):
            raise ValueError("invalid revision response provenance or size")
        parsed = ReplacementResponse.model_validate_json(result.text)
        replacements = {item.id: item.text for item in parsed.replacements}
        if len(replacements) != len(parsed.replacements) or set(replacements) != {
            s["id"] for s in spans
        }:
            raise ValueError("replacement IDs must match the exact allowed set")
        for index in reversed(range(len(intervals))):
            start, end = intervals[index]
            candidate = candidate[:start] + replacements[f"span-{index}"] + candidate[end:]
        if not candidate.strip() or len(candidate) > 12_000 or "\x00" in candidate:
            raise ValueError("replacement candidate cannot be stored")
        applied = candidate != content
        detail = "Only flagged spans were replaced; all other saved text is unchanged."
    except (ValidationError, ValueError):
        candidate = content
    return RevisionProposal(
        content=candidate,
        applied=applied,
        detail=detail,
        model=result.model,
        provider=result.provider.value,
        usage=result.usage,
        latency_ms=result.latency_ms,
    )
