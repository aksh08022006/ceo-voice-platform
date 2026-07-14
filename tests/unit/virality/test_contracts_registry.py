"""Adversarial virality contract and publication invariant tests."""

import asyncio
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.core.exceptions import StorageError
from ceo_voice.virality import (
    EvidenceSpan,
    EvidenceUnit,
    InMemoryViralityWorkspace,
    NormalizedPerformance,
    PerformanceBasis,
    PublicationStatus,
    StructuralFeatureDefinition,
    ValidationReport,
    Version,
    create_virality_builder,
)
from ceo_voice.virality.contracts import ValidationIssue
from ceo_voice.virality.enums import ValidationCode, ValidationSeverity
from tests.unit.analysis.factories import NOW, TENANT_ID
from tests.unit.virality.factories import corpus


def test_contracts_reject_ambiguous_registry_performance_and_evidence() -> None:
    profile = asyncio.run(
        create_virality_builder(workspace=InMemoryViralityWorkspace()).build(corpus(1, 2, 3, 4))
    )
    definition = profile.publication.release.patterns[0]
    from ceo_voice.virality.features import build_feature_registry

    source_definition = build_feature_registry().get(definition.feature)
    payload = source_definition.model_dump()
    payload["allowed_patterns"] = ("duplicate", "duplicate")
    with pytest.raises(ValidationError, match="must be unique"):
        StructuralFeatureDefinition.model_validate(payload)
    with pytest.raises(ValidationError, match="finite"):
        NormalizedPerformance(
            weighted_engagement=float("inf"),
            score_per_thousand=1,
            basis=PerformanceBasis.RAW_ENGAGEMENT,
            confounded=True,
            limitations=("Unnormalized.",),
            normalizer_version=Version(major=1, minor=0, patch=0),
        )
    with pytest.raises(ValidationError, match="end must exceed"):
        EvidenceSpan(
            id=UUID(int=1),
            tenant_id=TENANT_ID,
            corpus_id=UUID(int=2),
            document_id=UUID(int=3),
            document_version=1,
            unit=EvidenceUnit.DOCUMENT,
            start=2,
            end=1,
            text_hash="a" * 64,
        )


def test_corpus_contract_rejects_duplicate_and_cross_tenant_documents() -> None:
    selected = corpus(1, 2)
    with pytest.raises(ValidationError, match="unique by version"):
        selected.model_validate(
            selected.model_dump() | {"items": (selected.items[0], selected.items[0])}
        )
    wrong_document = selected.items[0].document.model_copy(update={"tenant_id": UUID(int=999)})
    with pytest.raises(ValidationError, match="share the tenant"):
        selected.model_validate(
            selected.model_dump()
            | {
                "items": (
                    selected.items[0].model_copy(update={"document": wrong_document}),
                    selected.items[1],
                )
            }
        )


def test_publication_and_profile_contracts_pin_one_valid_release() -> None:
    profile = asyncio.run(
        create_virality_builder(workspace=InMemoryViralityWorkspace()).build(corpus(1, 2, 3, 4))
    )
    publication = profile.publication
    mismatch = publication.validation.model_copy(update={"release_id": UUID(int=999)})
    with pytest.raises(ValidationError, match="must reference"):
        publication.model_validate(publication.model_dump() | {"validation": mismatch})
    invalid = ValidationReport(
        id=UUID(int=501),
        release_id=publication.release.id,
        validator_version=Version(major=1, minor=0, patch=0),
        issues=(
            ValidationIssue(
                code=ValidationCode.AGGREGATE,
                severity=ValidationSeverity.ERROR,
                message="Invalid.",
                path="release.patterns",
            ),
        ),
        validated_at=NOW,
    )
    with pytest.raises(ValidationError, match="cannot be published"):
        publication.model_validate(publication.model_dump() | {"validation": invalid})
    wrong_inspection = profile.inspection.model_copy(update={"release_id": UUID(int=998)})
    with pytest.raises(ValidationError, match="inspection must reference"):
        profile.model_validate(profile.model_dump() | {"inspection": wrong_inspection})
    wrong_version = profile.inspection.model_copy(update={"release_version": 99})
    with pytest.raises(ValidationError, match="inspection version"):
        profile.model_validate(profile.model_dump() | {"inspection": wrong_version})


def test_workspace_requires_active_monotonic_publication() -> None:
    workspace = InMemoryViralityWorkspace()
    profile = asyncio.run(create_virality_builder(workspace=workspace).build(corpus(1, 2, 3, 4)))
    inactive = profile.model_copy(
        update={
            "publication": profile.publication.model_copy(
                update={"status": PublicationStatus.SUPERSEDED}
            )
        }
    )
    with pytest.raises(StorageError, match="only an active"):
        asyncio.run(InMemoryViralityWorkspace().publish(inactive))
