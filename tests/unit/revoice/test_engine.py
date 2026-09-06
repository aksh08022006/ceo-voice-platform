"""Conservative Re-Voice orchestration, traceability, and failure tests."""

import asyncio
from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID

import pytest

from ceo_voice.context import CompiledConstraint
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
)
from ceo_voice.core.exceptions import ProviderError, ReVoiceError, ReVoiceValidationError
from ceo_voice.generation import GeneratedDraft
from ceo_voice.generation.contracts import (
    GenerationReport,
    ProviderRequest,
    ProviderResult,
    TokenUsage,
)
from ceo_voice.generation.enums import ProviderName
from ceo_voice.retrieval import InMemoryEvidenceMaterialReader, RetrievalIntelligenceEngine
from ceo_voice.revoice import EditedDraft, ReVoiceEngine, ReVoiceInput, ReVoicePolicy
from ceo_voice.revoice.analysis import DifferenceAnalyzer, RegionDetector
from ceo_voice.revoice.enums import ProtectionKind, ReVoiceAttemptKind, ReVoiceValidationCode
from tests.unit.retrieval.test_engine import _input as retrieval_input


class FakeProvider:
    name = ProviderName.OPENAI

    def __init__(self, outcomes: Iterable[str | ProviderError]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return ProviderResult(
            text=outcome,
            provider=self.name,
            model=request.model,
            provider_request_id="revoice-1",
            usage=TokenUsage(input_tokens=80, output_tokens=25),
            latency_ms=15,
        )


def revoice_input(
    *,
    original: str = "We build quickly.\n\nOwnership drives progress.\n\nTell me what you think?",
    edited: str = "We build quickly.\n\nOwnership creates momentum.\n\nTell me what you think?",
) -> ReVoiceInput:
    source, materials = retrieval_input(with_supplied_evidence=True)
    bundle = asyncio.run(
        RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(source)
    )
    draft = GeneratedDraft.model_construct(
        id=UUID(int=9100),
        request_id=source.request.request_id,
        content=original,
        thread=(original,),
        report=GenerationReport.model_construct(
            **cast(Any, {"retrieval_bundle_id": bundle.bundle_id})
        ),
        created_at=source.retrieved_at,
    )
    return ReVoiceInput(
        edited_draft=EditedDraft(
            original=draft,
            content=edited,
            edited_at=source.retrieved_at,
        ),
        context=source.context,
        retrieval=bundle,
        voice_profile=source.voice_profile,
        virality_profile=source.virality_profile,
        requested_at=source.retrieved_at,
    )


def engine(provider: FakeProvider, **changes: object) -> ReVoiceEngine:
    return ReVoiceEngine(
        provider,
        policy=ReVoicePolicy(
            provider=ProviderName.OPENAI,
            model="revoice-test-model",
            **changes,
        ),
    )


def test_restores_only_edited_line_and_reports_every_governed_input() -> None:
    provider = FakeProvider(
        ("We build quickly.\n\nOwnership compounds momentum.\n\nTell me what you think?",)
    )
    value = revoice_input()

    result = asyncio.run(engine(provider).restore(value))

    assert result.content == (
        "We build quickly.\n\nOwnership compounds momentum.\n\nTell me what you think?"
    )
    assert result.report.context_id == value.context.context_id
    assert result.report.retrieval_bundle_id == value.retrieval.bundle_id
    assert result.report.hvm_release_id == value.voice_profile.managed_release.release.id
    assert result.report.vkr_release_id == value.virality_profile.publication.release.id
    assert result.report.changed_regions == ("editable.line.2",)
    assert result.report.voice_features_strengthened
    assert result.report.final_validation.valid
    assert result.report.total_usage == TokenUsage(input_tokens=80, output_tokens=25)
    assert "You are" not in provider.requests[0].system
    assert "editable_lines" in provider.requests[0].user
    assert "protected_regions" in provider.requests[0].user


def test_protected_fact_and_cta_change_triggers_targeted_validation_retry() -> None:
    original = "A useful benchmark.\n\nDatabricks grew 42% in 2025.\n\nRead the report?"
    edited = "A useful benchmark.\n\nDatabricks scaled 42% in 2025.\n\nRead the report?"
    provider = FakeProvider(
        (
            "A useful benchmark.\n\nThe company scaled 50% in 2026.\n\nRead the report?",
            "A useful benchmark.\n\nDatabricks compounded 42% in 2025.\n\nRead the report?",
        )
    )

    result = asyncio.run(engine(provider).restore(revoice_input(original=original, edited=edited)))

    first = result.report.attempts[0]
    assert first.validation is not None
    assert ReVoiceValidationCode.PROTECTED_TEXT_CHANGED in {
        item.code for item in first.validation.findings
    }
    assert result.report.attempts[1].kind is ReVoiceAttemptKind.VALIDATION_REPAIR
    assert "repair_only" in provider.requests[1].user
    assert result.content.endswith("Read the report?")


def test_transient_provider_failure_retries_the_identical_prompt() -> None:
    provider = FakeProvider(
        (
            ProviderError("rate limited", retryable=True),
            "We build quickly.\n\nOwnership compounds momentum.\n\nTell me what you think?",
        )
    )

    result = asyncio.run(engine(provider).restore(revoice_input()))

    assert provider.requests[0] == provider.requests[1]
    assert result.report.attempts[1].kind is ReVoiceAttemptKind.PROVIDER_RETRY


def test_invalid_restoration_preserves_valid_human_edit_after_validation_budget() -> None:
    provider = FakeProvider(("Replaced everything.",))
    value = revoice_input()

    result = asyncio.run(engine(provider, maximum_validation_retries=0).restore(value))

    assert result.content == value.edited_draft.content
    assert result.report.changed_regions == ()
    assert len(result.report.attempts) == 1
    assert result.report.attempts[0].validation is not None
    assert not result.report.attempts[0].validation.valid
    assert result.report.final_validation.valid
    assert result.report.confidence == 0


def test_invalid_human_edit_is_rejected_before_provider_call_with_actionable_limit() -> None:
    provider = FakeProvider(("unused",))
    value = revoice_input(
        original="Keep this.",
        edited="Keep this.\n\nThis addition exceeds the tiny compiled platform budget.",
    )
    constrained_platform = value.context.platform.model_copy(update={"maximum_characters": 20})
    constrained_context = value.context.model_copy(update={"platform": constrained_platform})

    with pytest.raises(ReVoiceValidationError, match=r"characters.*over.*20-character") as error:
        asyncio.run(
            engine(provider).restore(value.model_copy(update={"context": constrained_context}))
        )

    assert error.value.details["maximum_characters"] == 20
    assert cast(int, error.value.details["characters_over"]) > 0
    assert error.value.details["findings"] == (ReVoiceValidationCode.PLATFORM_LENGTH.value,)
    assert not provider.requests


def test_nonretryable_and_exhausted_provider_failures_propagate() -> None:
    with pytest.raises(ProviderError, match="bad request"):
        asyncio.run(engine(FakeProvider((ProviderError("bad request"),))).restore(revoice_input()))
    provider = FakeProvider(
        (
            ProviderError("rate limited", retryable=True),
            ProviderError("rate limited again", retryable=True),
        )
    )
    with pytest.raises(ProviderError, match="again"):
        asyncio.run(engine(provider, maximum_provider_retries=1).restore(revoice_input()))


def test_no_human_changes_returns_an_audited_noop_without_model_call() -> None:
    content = "Nothing changed.\n\nKeep this exact."
    provider = FakeProvider(())

    result = asyncio.run(engine(provider).restore(revoice_input(original=content, edited=content)))

    assert result.content == content
    assert result.report.changed_regions == ()
    assert result.report.voice_features_strengthened == ()
    assert result.report.attempts == ()
    assert result.report.confidence == 1
    assert not provider.requests


def test_deletion_only_preserves_human_structure_without_model_call() -> None:
    provider = FakeProvider(())
    value = revoice_input(
        original="Keep this.\n\nHuman removed this.\n\nKeep the ending.",
        edited="Keep this.\n\nKeep the ending.",
    )

    result = asyncio.run(engine(provider).restore(value))

    assert result.content == value.edited_draft.content
    assert result.report.difference.changes
    assert result.report.regions.editable == ()
    assert not provider.requests


def test_mismatched_lineage_is_rejected_before_provider_call() -> None:
    value = revoice_input()
    provider = FakeProvider(("unused",))
    invalid_context = value.context.model_copy(
        update={"voice": value.context.voice.model_copy(update={"release_id": UUID(int=99999)})}
    )

    with pytest.raises(ReVoiceError, match="incompatible"):
        asyncio.run(engine(provider).restore(value.model_copy(update={"context": invalid_context})))
    assert not provider.requests


def test_provider_policy_must_match() -> None:
    provider = FakeProvider(())
    policy = ReVoicePolicy(
        provider=ProviderName.ANTHROPIC,
        model="wrong-provider",
    )
    with pytest.raises(ValueError, match="agree"):
        ReVoiceEngine(provider, policy=policy)
    with pytest.raises(ValueError, match="output budget"):
        ReVoicePolicy(
            provider=ProviderName.OPENAI,
            model="invalid-window",
            model_context_tokens=512,
            maximum_output_tokens=512,
        )


def test_mandatory_revoice_context_must_fit_model_window() -> None:
    provider = FakeProvider(("unused",))
    with pytest.raises(ReVoiceValidationError, match="model context"):
        asyncio.run(
            engine(
                provider,
                model_context_tokens=512,
                maximum_output_tokens=500,
            ).restore(revoice_input())
        )
    assert not provider.requests


def test_analysis_detects_changes_and_protects_semantic_anchors() -> None:
    original = "Old sentence."
    edited = (
        "New Acme Corp sentence with 25%, @owner, #launch, `code`, "
        '"quoted fact", [source](https://example.com), and team@example.com.'
    )
    difference = DifferenceAnalyzer().analyze(original, edited)
    regions = RegionDetector().detect(edited, difference)

    assert difference.changes
    assert difference.changed_line_indices == (0,)
    assert regions.editable[0].content == edited
    assert {item.kind for item in regions.protected} >= {
        ProtectionKind.PROPER_NOUN,
        ProtectionKind.NUMBER,
        ProtectionKind.SOCIAL_REFERENCE,
        ProtectionKind.INLINE_CODE,
        ProtectionKind.QUOTATION,
        ProtectionKind.MARKDOWN_LINK,
        ProtectionKind.EMAIL,
    }


def test_validator_rejects_format_structure_safety_budget_and_hard_constraint_drift() -> None:
    value = revoice_input(
        original="- Original line.\n\nStable ending.",
        edited="- Human edited line.\n\nStable ending.",
    )
    hard = CompiledConstraint(
        constraint_id="content.required.term",
        category=ConstraintCategory.USER,
        strength=ConstraintStrength.HARD,
        operator=ConstraintOperator.EQUALS,
        key="content.required.term",
        value="required-term",
        priority=100,
        source="test",
        rationale="test deterministic constraint",
    )
    context = value.context.model_copy(
        update={
            "constraints": value.context.constraints.model_copy(
                update={"constraints": (*value.context.constraints.constraints, hard)}
            )
        }
    )
    constrained = value.model_copy(update={"context": context})
    regions = RegionDetector().detect(
        constrained.edited_draft.content,
        DifferenceAnalyzer().analyze(
            constrained.edited_draft.original.content, constrained.edited_draft.content
        ),
    )
    candidate = "Changed all formatting and kill yourself.\x01"
    validation = engine(FakeProvider(()))._validator.validate(
        candidate,
        constrained,
        regions,
        ReVoicePolicy(
            provider=ProviderName.OPENAI,
            model="test",
            maximum_changed_fraction=0.1,
        ),
    )

    codes = {item.code for item in validation.findings}
    assert codes >= {
        ReVoiceValidationCode.STRUCTURE_CHANGED,
        ReVoiceValidationCode.PROTECTED_TEXT_CHANGED,
        ReVoiceValidationCode.CHANGE_BUDGET_EXCEEDED,
        ReVoiceValidationCode.UNSAFE_CONTENT,
        ReVoiceValidationCode.INVALID_CONTROL_CHARACTER,
        ReVoiceValidationCode.HARD_CONSTRAINT_VIOLATED,
    }
    assert not validation.valid


def test_second_pass_protects_prior_voice_changes_and_only_refines_the_new_edit() -> None:
    value = revoice_input()
    first_text = "We build quickly.\n\nOwnership compounds momentum.\n\nTell me what you think?"
    first = asyncio.run(engine(FakeProvider((first_text,))).restore(value))
    second_edit = first_text.replace("We build quickly.", "We build carefully.")
    proposed = second_edit.replace("carefully", "deliberately")
    provider = FakeProvider((proposed.replace("compounds", "creates"), proposed))
    revision = EditedDraft(
        original=value.edited_draft.original,
        previous_revision=first,
        content=second_edit,
        edited_at=value.requested_at,
    )
    result = asyncio.run(
        engine(provider).restore(value.model_copy(update={"edited_draft": revision}))
    )
    assert result.content == proposed
    assert result.report.difference.changed_line_indices == (0,)
    assert result.report.changed_regions == ("editable.line.0",)
    assert result.report.attempts[0].validation is not None
    assert not result.report.attempts[0].validation.valid
    assert "Ownership compounds momentum." in result.content
    assert result.original_draft_id == value.edited_draft.original.id


def test_previous_revision_must_have_matching_generation_and_profile_lineage() -> None:
    value = revoice_input()
    first = asyncio.run(engine(FakeProvider((value.edited_draft.content,))).restore(value))
    with pytest.raises(ValueError, match="previous revision must belong"):
        EditedDraft(
            original=value.edited_draft.original,
            previous_revision=first.model_copy(update={"original_draft_id": UUID(int=99999)}),
            content=first.content,
            edited_at=value.requested_at,
        )
    invalid_previous = first.model_copy(
        update={"report": first.report.model_copy(update={"hvm_release_id": UUID(int=99999)})}
    )
    revised = EditedDraft(
        original=value.edited_draft.original,
        previous_revision=invalid_previous,
        content=first.content,
        edited_at=value.requested_at,
    )
    provider = FakeProvider(())
    with pytest.raises(ReVoiceError, match="incompatible"):
        asyncio.run(engine(provider).restore(value.model_copy(update={"edited_draft": revised})))
    assert not provider.requests
