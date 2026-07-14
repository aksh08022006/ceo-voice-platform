"""Fail-closed validation tests for pinned compiler inputs and local policies."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.context import (
    ContextCompilationError,
    ContextCompilerVersion,
    EvidenceCompiler,
    PlatformContract,
    PlatformContractCatalog,
    UserConstraint,
    create_context_compiler,
)
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
)
from ceo_voice.models.enums import ContextRole, Platform
from ceo_voice.models.retrieval import RetrievedContext, RetrievedItem
from ceo_voice.virality import PublicationStatus
from ceo_voice.virality.contracts import ValidationIssue
from ceo_voice.virality.enums import ValidationCode, ValidationSeverity
from tests.unit.context.factories import compilation_input
from tests.unit.voice.factories import NOW


def test_compiler_rejects_mismatched_pinned_artifacts_and_lifecycle_states() -> None:
    compiler = create_context_compiler()
    complete = compilation_input()
    assert complete.voice_release is not None
    assert complete.virality_profile is not None

    inactive_voice = complete.voice_release.model_copy(
        update={"events": complete.voice_release.events[:1], "validation_report": None}
    )
    no_voice_report = complete.voice_release.model_copy(update={"validation_report": None})
    inactive_publication = complete.virality_profile.publication.model_copy(
        update={"status": PublicationStatus.SUPERSEDED}
    )
    inactive_virality = complete.virality_profile.model_copy(
        update={"publication": inactive_publication}
    )
    validation = complete.virality_profile.publication.validation
    invalid_validation = validation.model_copy(
        update={
            "issues": (
                ValidationIssue(
                    code=ValidationCode.OWNERSHIP,
                    severity=ValidationSeverity.ERROR,
                    message="tenant mismatch",
                    path="release.tenant_id",
                ),
            )
        }
    )
    invalid_virality = complete.virality_profile.model_copy(
        update={
            "publication": complete.virality_profile.publication.model_copy(
                update={"validation": invalid_validation}
            )
        }
    )
    mismatched_registry = complete.feature_registry.model_copy(update={"id": UUID(int=9999)})
    cases = (
        (complete.model_copy(update={"voice_release": inactive_voice}), "inactive_voice_profile"),
        (complete.model_copy(update={"voice_release": no_voice_report}), "invalid_voice_profile"),
        (
            complete.model_copy(update={"virality_profile": inactive_virality}),
            "inactive_virality_profile",
        ),
        (
            complete.model_copy(update={"virality_profile": invalid_virality}),
            "invalid_virality_profile",
        ),
        (
            complete.model_copy(
                update={"request": complete.request.model_copy(update={"tenant_id": UUID(int=8)})}
            ),
            "ownership_mismatch",
        ),
        (
            complete.model_copy(
                update={
                    "target_identity": complete.target_identity.model_copy(
                        update={"leader_id": UUID(int=8)}
                    )
                }
            ),
            "identity_mismatch",
        ),
        (
            complete.model_copy(
                update={
                    "request": complete.request.model_copy(update={"voice_profile_id": UUID(int=8)})
                }
            ),
            "voice_profile_mismatch",
        ),
        (
            complete.model_copy(
                update={"request": complete.request.model_copy(update={"voice_profile_version": 2})}
            ),
            "voice_profile_version_mismatch",
        ),
        (
            complete.model_copy(update={"feature_registry": mismatched_registry}),
            "registry_mismatch",
        ),
    )

    for invalid, reason in cases:
        with pytest.raises(ContextCompilationError) as caught:
            compiler.compile(invalid)
        assert caught.value.details["reason"] == reason


def test_platform_catalog_and_contracts_validate_configuration() -> None:
    contract = PlatformContract(
        platform=Platform.LINKEDIN,
        version=ContextCompilerVersion(major=1, minor=0, patch=0),
        maximum_characters=3_000,
        thread_output_supported=False,
        source_name="Policy",
        source_reference="https://example.test/policy",
        verified_on=NOW.date(),
    )
    catalog = PlatformContractCatalog((contract,))

    assert catalog.get(Platform.LINKEDIN) == contract
    with pytest.raises(ContextCompilationError) as caught:
        catalog.get(Platform.GENERIC)
    assert caught.value.details["reason"] == "unsupported_request"
    with pytest.raises(ValueError, match="duplicate platform"):
        PlatformContractCatalog((contract, contract))
    with pytest.raises(ValueError, match="at least one"):
        PlatformContractCatalog(())
    with pytest.raises(ValidationError, match="thread support"):
        contract.model_copy(
            update={"thread_output_supported": True, "maximum_thread_posts": None}
        ).model_validate(
            contract.model_copy(
                update={"thread_output_supported": True, "maximum_thread_posts": None}
            ).model_dump()
        )
    assert str(contract.version) == "1.0.0"


def test_user_constraint_and_retrieved_evidence_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError, match="caller constraints"):
        UserConstraint(
            constraint_id="bad-category",
            category=ConstraintCategory.SAFETY,
            strength=ConstraintStrength.HARD,
            operator=ConstraintOperator.EQUALS,
            key="safety.rule",
            value=True,
            rationale="not caller-owned",
        )
    duplicate_pair = RetrievedContext(
        trace_id=UUID(int=901),
        query="duplicate",
        items=(
            RetrievedItem(
                document_id=UUID(int=902),
                content="one",
                role=ContextRole.VOICE_EVIDENCE,
                score=1,
                rank=1,
            ),
            RetrievedItem(
                document_id=UUID(int=902),
                content="two",
                role=ContextRole.VOICE_EVIDENCE,
                score=0.5,
                rank=2,
            ),
        ),
        generated_at=NOW,
    )
    duplicate_rank = duplicate_pair.model_copy(
        update={
            "items": (
                duplicate_pair.items[0],
                duplicate_pair.items[1].model_copy(
                    update={"document_id": UUID(int=903), "rank": 1}
                ),
            )
        }
    )
    for invalid in (duplicate_pair, duplicate_rank):
        with pytest.raises(ContextCompilationError) as caught:
            EvidenceCompiler().compile(invalid, allowed_factual_document_ids=())
        assert caught.value.details["reason"] == "invalid_retrieved_evidence"
