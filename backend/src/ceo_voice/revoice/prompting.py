"""Prompt-last rendering from sealed Re-Voice decisions."""

from typing import cast

from pydantic import JsonValue

from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.revoice.contracts import RegionPlan, ReVoiceInput
from ceo_voice.utils.json import dumps_json

SYSTEM_INSTRUCTIONS = (
    "Restore observable writing-style features only inside the declared editable lines. "
    "Do not impersonate or mention the leader. Preserve meaning, factual claims, paragraph and "
    "line order, formatting, thread boundaries, CTA intent, and every protected value exactly. "
    "Return the complete revised draft as plain text and nothing else. If no safe improvement is "
    "possible, return the edited draft unchanged."
)


class ReVoicePromptBuilder:
    """Render only retrieval-approved knowledge and deterministic edit permissions."""

    def build(
        self,
        value: ReVoiceInput,
        regions: RegionPlan,
        *,
        repair_feedback: tuple[str, ...] = (),
    ) -> tuple[str, str]:
        payload = {
            "edited_draft": value.edited_draft.content,
            "editable_lines": [item.model_dump(mode="json") for item in regions.editable],
            "protected_regions": [item.model_dump(mode="json") for item in regions.protected],
            "voice_targets": [
                {
                    "feature_id": item.feature_id,
                    "target": item.target_value,
                    "confidence": item.confidence.selection_score,
                }
                for item in value.retrieval.voice_features
            ],
            "voice_evidence": [
                {
                    "evidence_id": str(item.evidence_id),
                    "text": item.content,
                    "why_selected": item.explanation.reason,
                    "supporting_features": list(item.explanation.supporting_feature_ids),
                }
                for item in value.retrieval.evidence
                if EvidencePurpose.VOICE_SUPPORT in item.purposes
            ],
            "negative_and_user_constraints": [
                item.model_dump(mode="json") for item in value.retrieval.constraints.constraints
            ],
            "platform": value.context.platform.model_dump(mode="json"),
            "repair_only": list(repair_feedback),
        }
        return SYSTEM_INSTRUCTIONS, dumps_json(cast(JsonValue, payload))
