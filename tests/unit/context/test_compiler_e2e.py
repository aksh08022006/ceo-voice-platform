"""End-to-end Context Compiler behavior and boundary validation."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.context import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
    ContextCompilationError,
    TraceArtifactKind,
    UserConstraint,
    create_context_compiler,
)
from ceo_voice.models.enums import ContextRole, Platform
from ceo_voice.models.retrieval import RetrievedContext, RetrievedItem
from tests.unit.context.factories import (
    compilation_input,
    generation_request,
    virality_profile,
)
from tests.unit.voice.factories import NOW


def test_compiler_builds_deterministic_separated_generation_context() -> None:
    compiler = create_context_compiler()
    compilation = compilation_input()

    first = compiler.compile(compilation)
    second = compiler.compile(compilation)

    assert second == first
    assert first.context_id == second.context_id
    assert len(first.content_hash) == 64
    assert first.voice.platform is Platform.LINKEDIN
    assert first.voice.features[0].feature_id == "lexical.function-word-rate"
    assert first.voice.release_id != first.virality.release_id
    assert len(first.virality.guidance) == 8
    assert first.virality.causal_claims_permitted is False
    assert first.constraints.summary.hard == 3
    assert first.constraints.summary.soft == 1
    assert first.report.selected_voice_feature_ids == ("lexical.function-word-rate",)
    trace_kinds = {item.kind for item in first.report.traceability}
    assert trace_kinds >= {
        TraceArtifactKind.HVM_RELEASE,
        TraceArtifactKind.HVM_COMPONENT,
        TraceArtifactKind.HVM_EVIDENCE,
        TraceArtifactKind.VKR_RELEASE,
        TraceArtifactKind.VKR_PATTERN,
        TraceArtifactKind.VKR_EVIDENCE,
    }
    serialized = first.model_dump()
    assert "prompt" not in serialized
    assert "model" not in serialized


def test_generation_context_rejects_tampered_hash_id_and_nested_summaries() -> None:
    result = create_context_compiler().compile(compilation_input())
    payload = result.model_dump(mode="json")

    with pytest.raises(ValidationError, match="content hash"):
        type(result).model_validate({**payload, "content_hash": "0" * 64})
    with pytest.raises(ValidationError, match="context ID"):
        type(result).model_validate({**payload, "context_id": str(UUID(int=999))})

    constraints = result.constraints.model_dump(mode="json")
    constraints["summary"]["total"] += 1
    with pytest.raises(ValidationError, match="constraint summary"):
        type(result.constraints).model_validate(constraints)

    evidence = result.evidence.model_dump(mode="json")
    evidence["lanes"] = tuple(reversed(evidence["lanes"]))
    with pytest.raises(ValidationError, match="canonical order"):
        type(result.evidence).model_validate(evidence)


def test_conflicting_hard_constraints_fail_before_context_assembly() -> None:
    conflict = UserConstraint(
        constraint_id="user.minimum.characters",
        category=ConstraintCategory.FORMATTING,
        strength=ConstraintStrength.HARD,
        operator=ConstraintOperator.MINIMUM,
        key="output.character_count",
        value=4_000,
        priority=80,
        rationale="Caller requested a long-form post",
    )

    with pytest.raises(ContextCompilationError) as caught:
        create_context_compiler().compile(compilation_input(user_constraints=(conflict,)))

    assert caught.value.details["reason"] == "constraint_conflict"
    assert caught.value.details["conflicts"] == ("output.character_count:minimum_exceeds_maximum",)


def test_supplied_evidence_is_partitioned_and_factual_sources_are_pinned() -> None:
    request = generation_request()
    factual_id = request.source_document_ids[0]
    evidence = RetrievedContext(
        trace_id=UUID(int=701),
        query="ownership execution evidence",
        items=(
            RetrievedItem(
                document_id=factual_id,
                content="Clear ownership reduced time to resolution.",
                role=ContextRole.FACTUAL_EVIDENCE,
                score=0.91,
                rank=1,
            ),
            RetrievedItem(
                document_id=UUID(int=702),
                content="A short representative voice passage.",
                role=ContextRole.VOICE_EVIDENCE,
                score=0.82,
                rank=2,
            ),
        ),
        generated_at=NOW,
    )

    result = create_context_compiler().compile(
        compilation_input(request=request, retrieved_evidence=evidence)
    )

    lanes = {lane.role: lane.items for lane in result.evidence.lanes}
    assert lanes[ContextRole.FACTUAL_EVIDENCE][0].document_id == factual_id
    assert lanes[ContextRole.VOICE_EVIDENCE][0].document_id == UUID(int=702)
    assert any(item.kind is TraceArtifactKind.RETRIEVAL for item in result.report.traceability)

    unpinned = evidence.model_copy(
        update={
            "items": (
                evidence.items[0].model_copy(update={"document_id": UUID(int=999)}),
                evidence.items[1],
            )
        }
    )
    with pytest.raises(ContextCompilationError) as caught:
        create_context_compiler().compile(
            compilation_input(request=request, retrieved_evidence=unpinned)
        )
    assert caught.value.details["reason"] == "unpinned_factual_evidence"


def test_missing_profiles_and_platform_mismatch_have_stable_failure_reasons() -> None:
    complete = compilation_input()
    missing_voice = complete.model_copy(update={"voice_release": None})
    missing_virality = complete.model_copy(update={"virality_profile": None})

    for invalid, reason in (
        (missing_voice, "missing_voice_profile"),
        (missing_virality, "missing_virality_profile"),
    ):
        with pytest.raises(ContextCompilationError) as caught:
            create_context_compiler().compile(invalid)
        assert caught.value.details["reason"] == reason

    x_request = generation_request(platform=Platform.X)
    with pytest.raises(ContextCompilationError) as caught:
        create_context_compiler().compile(
            compilation_input(request=x_request, virality=virality_profile())
        )
    assert caught.value.details["reason"] == "platform_mismatch"
