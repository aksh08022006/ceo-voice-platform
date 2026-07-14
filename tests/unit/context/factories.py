"""Deterministic fixtures for context-compilation tests."""

import asyncio
from datetime import timedelta
from uuid import UUID

from ceo_voice.context import CompilationInput, UserConstraint
from ceo_voice.models.enums import Platform
from ceo_voice.models.retrieval import RetrievedContext
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.virality import InMemoryViralityWorkspace, ViralityProfile, create_virality_builder
from ceo_voice.voice import (
    HVMRelease,
    ManagedRelease,
    ReleaseEvent,
    ReleaseEventType,
    ValidationReport,
)
from tests.unit.virality.factories import corpus
from tests.unit.voice.factories import (
    ACTOR_ID,
    LEADER_ID,
    LINEAGE_ID,
    NOW,
    TENANT_ID,
    identity,
    registry,
    release,
    validation_report,
)


def active_voice_release(
    *, release_value: HVMRelease | None = None, report: ValidationReport | None = None
) -> ManagedRelease:
    """Return a validated, approved, active HVM release stream."""

    selected = release_value or release()
    selected_report = report or validation_report(release_value=selected)
    events = (
        ReleaseEvent(
            id=UUID(int=501),
            release_id=selected.id,
            sequence=1,
            event_type=ReleaseEventType.CREATED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        ),
        ReleaseEvent(
            id=UUID(int=502),
            release_id=selected.id,
            sequence=2,
            event_type=ReleaseEventType.VALIDATION_STARTED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        ),
        ReleaseEvent(
            id=UUID(int=503),
            release_id=selected.id,
            sequence=3,
            event_type=ReleaseEventType.VALIDATION_PASSED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
            validation_report_id=selected_report.id,
        ),
        ReleaseEvent(
            id=UUID(int=504),
            release_id=selected.id,
            sequence=4,
            event_type=ReleaseEventType.APPROVED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        ),
        ReleaseEvent(
            id=UUID(int=505),
            release_id=selected.id,
            sequence=5,
            event_type=ReleaseEventType.ACTIVATED,
            actor_id=ACTOR_ID,
            occurred_at=NOW,
        ),
    )
    return ManagedRelease(
        release=selected,
        events=events,
        validation_report=selected_report,
    )


def virality_profile() -> ViralityProfile:
    """Build a supported multi-leader LinkedIn VKR fixture."""

    source = corpus(1, 2, 3, 4)
    tenant_aligned = source.model_copy(
        update={
            "tenant_id": TENANT_ID,
            "items": tuple(
                item.model_copy(
                    update={"document": item.document.model_copy(update={"tenant_id": TENANT_ID})}
                )
                for item in source.items
            ),
        }
    )
    return asyncio.run(
        create_virality_builder(workspace=InMemoryViralityWorkspace()).build(tenant_aligned)
    )


def generation_request(*, platform: Platform = Platform.LINKEDIN) -> GenerationRequest:
    """Return a request pinned to the voice fixture lineage and version."""

    return GenerationRequest(
        request_id=UUID(int=601),
        tenant_id=TENANT_ID,
        ceo_id=LEADER_ID,
        voice_profile_id=LINEAGE_ID,
        voice_profile_version=1,
        platform=platform,
        topic="How clear ownership improves execution",
        objective="Teach operating leaders",
        audience="technology executives",
        source_document_ids=(UUID(int=602),),
        constraints=("Avoid unsupported superlatives",),
    )


def compilation_input(
    *,
    request: GenerationRequest | None = None,
    voice: ManagedRelease | None = None,
    virality: ViralityProfile | None = None,
    user_constraints: tuple[UserConstraint, ...] = (),
    retrieved_evidence: RetrievedContext | None = None,
) -> CompilationInput:
    """Return complete pinned compiler input while allowing explicit missing artifacts."""

    return CompilationInput(
        request=request or generation_request(),
        target_identity=identity(),
        voice_release=voice if voice is not None else active_voice_release(),
        feature_registry=registry(),
        virality_profile=virality if virality is not None else virality_profile(),
        retrieved_evidence=retrieved_evidence,
        user_constraints=user_constraints,
        compiled_at=NOW + timedelta(hours=1),
    )
