"""Structured prompt assembly, evidence budgeting, and final rendering."""

from uuid import UUID

from pydantic import JsonValue

from ceo_voice.core.exceptions import PromptBudgetError
from ceo_voice.generation.contracts import (
    GenerationInput,
    GenerationPolicy,
    PromptSection,
    RenderedPrompt,
    StructuredPrompt,
)
from ceo_voice.generation.enums import PromptSectionKind
from ceo_voice.prompts import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, THREAD_SEPARATOR
from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.utils.json import dumps_json

_COMPOSITION_ROUTES = (
    "lead with the concrete outcome, then explain the mechanism",
    "lead with the core claim, then support it with evidence",
    "lead with the operating problem, then show what changed",
    "lead with the technical mechanism, then connect it to the practical consequence",
    "lead with a specific observation, then widen to the strategic implication",
)


def _variation_directive(request_id: UUID) -> dict[str, JsonValue]:
    """Return a traceable composition choice without adding a caller-facing input."""

    route = _COMPOSITION_ROUTES[request_id.int % len(_COMPOSITION_ROUTES)]
    return {
        "variation_key": str(request_id),
        "composition_route": route,
        "instruction": (
            "Write fresh wording for this request. Do not reuse a stock hook, stock closing, "
            "or question-led frame merely because it appeared in an example."
        ),
    }


class TokenBudgetManager:
    """Fit optional evidence by retrieval rank after reserving all governed guidance."""

    def __init__(self, policy: GenerationPolicy) -> None:
        self._policy = policy

    def fit(
        self, mandatory: tuple[PromptSection, ...], evidence: tuple[PromptSection, ...]
    ) -> tuple[tuple[PromptSection, ...], tuple[str, ...]]:
        available = self._policy.model_context_tokens - self._policy.maximum_output_tokens
        selected = list(mandatory)
        used = sum(self.estimate(item.content) for item in mandatory)
        if used > available:
            raise PromptBudgetError(
                "mandatory generation guidance exceeds model context",
                details={"estimated_tokens": used, "available_tokens": available},
            )
        pruned: list[str] = []
        for section in evidence:
            cost = self.estimate(section.content)
            if used + cost <= available:
                selected.append(section)
                used += cost
            else:
                pruned.extend(str(item) for item in section.source_ids)
        return tuple(selected), tuple(pruned)

    def estimate(self, content: str) -> int:
        return max(1, int(len(content) / self._policy.estimated_characters_per_token) + 1)


class PromptBuilder:
    """Project governed targets into sections without inventing a persona summary."""

    def __init__(self, budget: TokenBudgetManager) -> None:
        self._budget = budget

    def build(
        self, value: GenerationInput, *, repair_feedback: tuple[str, ...] = ()
    ) -> StructuredPrompt:
        context, bundle = value.context, value.retrieval
        system = PromptSection(
            kind=PromptSectionKind.SYSTEM,
            mandatory=True,
            priority=100,
            content=SYSTEM_INSTRUCTIONS,
        )
        voice = PromptSection(
            kind=PromptSectionKind.VOICE,
            mandatory=True,
            priority=95,
            source_ids=tuple(
                item for feature in bundle.voice_features for item in feature.component_ids
            ),
            content=dumps_json(
                {
                    "voice_targets": [
                        {
                            "feature": item.feature_id,
                            "dimension": item.dimension.value,
                            "target": item.target_value,
                            "confidence": item.confidence.selection_score,
                        }
                        for item in bundle.voice_features
                    ],
                    "negative_and_user_constraints": [
                        item.model_dump(mode="json") for item in bundle.constraints.constraints
                    ],
                }
            ),
        )
        structure = PromptSection(
            kind=PromptSectionKind.STRUCTURE,
            mandatory=True,
            priority=90,
            source_ids=tuple(item.pattern_id for item in bundle.structural_guidance),
            content=dumps_json(
                {
                    "influence": context.virality.influence,
                    "instruction": (
                        "Apply structural guidance proportionally and never override voice targets"
                    ),
                    "structure_targets": [
                        {
                            "dimension": item.dimension.value,
                            "pattern": item.pattern_key,
                            "label": item.label,
                        }
                        for item in bundle.structural_guidance
                    ],
                }
            ),
        )
        request = PromptSection(
            kind=PromptSectionKind.REQUEST,
            mandatory=True,
            priority=100,
            source_ids=(value.request.request_id,),
            content=dumps_json(
                {
                    "topic": value.request.topic,
                    "objective": value.request.objective,
                    "audience": value.request.audience,
                    "platform": value.request.platform.value,
                    "content_type": value.request.content_type.value,
                    "thread_post_count": value.request.thread_post_count,
                    "candidate_number": 1,
                    "variation": _variation_directive(value.request.request_id),
                    "topic_requirement": (
                        "The draft must directly address this topic in every paragraph. Preserve at "
                        "least one of its concrete anchor terms; do not substitute a topic found in "
                        "voice or structural examples."
                    ),
                }
            ),
        )
        output = PromptSection(
            kind=PromptSectionKind.OUTPUT,
            mandatory=True,
            priority=100,
            content=dumps_json(
                {
                    "maximum_characters_per_post": context.platform.maximum_characters,
                    "thread_supported": context.platform.thread_output_supported,
                    "maximum_thread_posts": context.platform.maximum_thread_posts,
                    "requested_thread_posts": value.request.thread_post_count,
                    "minimum_words": value.request.minimum_words,
                    "maximum_words": value.request.maximum_words,
                    "thread_separator": THREAD_SEPARATOR,
                    "format": "plain text only",
                    "hard_requirement": (
                        f"Return exactly one post of at most "
                        f"{context.platform.maximum_characters} characters, including spaces "
                        "and line breaks. Do not add commentary before or after it."
                        if value.request.thread_post_count is None
                        else (
                            "Every thread post must remain within the supplied character limit "
                            "and posts must use only the supplied separator."
                        )
                    ),
                }
            ),
        )
        mandatory = [system, voice, structure, request, output]
        if repair_feedback:
            mandatory.append(
                PromptSection(
                    kind=PromptSectionKind.REPAIR,
                    mandatory=True,
                    priority=100,
                    content=dumps_json(
                        {
                            "repair_only_these_validation_failures": list(repair_feedback),
                            "preserve_all_other_requirements": True,
                        }
                    ),
                )
            )
        evidence = tuple(
            PromptSection(
                kind=PromptSectionKind.EVIDENCE,
                mandatory=False,
                priority=item.priority,
                source_ids=(item.evidence_id,),
                content=dumps_json(
                    {
                        "evidence_id": str(item.evidence_id),
                        "purposes": [purpose.value for purpose in item.purposes],
                        "content_authority": (
                            "factual_source"
                            if EvidencePurpose.FACTUAL_SUPPORT in item.purposes
                            else "style_only"
                        ),
                        "text": item.content,
                        "why_selected": item.explanation.reason,
                        "use_restriction": (
                            "May support factual claims in the requested topic."
                            if EvidencePurpose.FACTUAL_SUPPORT in item.purposes
                            else (
                                "Use only as evidence of writing behavior or structure. Do not "
                                "reuse its topic, entities, events, metrics, or claims."
                            )
                        ),
                    }
                ),
            )
            for item in bundle.evidence
        )
        required_purposes = {
            EvidencePurpose.VOICE_SUPPORT,
            EvidencePurpose.STRUCTURAL_SUPPORT,
            EvidencePurpose.FACTUAL_SUPPORT,
        }
        reserved_ids = {
            next((item.evidence_id for item in bundle.evidence if purpose in item.purposes), None)
            for purpose in required_purposes
        }
        reserved_ids.discard(None)
        reserved = tuple(
            item.model_copy(update={"mandatory": True})
            for item in evidence
            if item.source_ids[0] in reserved_ids
        )
        optional = tuple(item for item in evidence if item.source_ids[0] not in reserved_ids)
        selected, pruned = self._budget.fit((*mandatory, *reserved), optional)
        included = tuple(
            item.source_ids[0] for item in selected if item.kind is PromptSectionKind.EVIDENCE
        )
        return StructuredPrompt(
            version=PROMPT_VERSION,
            sections=selected,
            included_evidence_ids=included,
            pruned_evidence_ids=tuple(UUID(item) for item in pruned),
        )


class PromptRenderer:
    """Render sections only after selection and budgeting are complete."""

    def __init__(self, budget: TokenBudgetManager) -> None:
        self._budget = budget

    def render(self, prompt: StructuredPrompt) -> RenderedPrompt:
        system = "\n\n".join(
            item.content for item in prompt.sections if item.kind is PromptSectionKind.SYSTEM
        )
        user = "\n\n".join(
            f"[{item.kind.value.upper()}]\n{item.content}"
            for item in prompt.sections
            if item.kind is not PromptSectionKind.SYSTEM
        )
        return RenderedPrompt(
            version=prompt.version,
            system=system,
            user=user,
            estimated_input_tokens=self._budget.estimate(system + "\n" + user),
            included_evidence_ids=prompt.included_evidence_ids,
            pruned_evidence_ids=prompt.pruned_evidence_ids,
        )
