"""End-to-end retrieval, determinism, validation, and budget tests."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from ceo_voice.context import create_context_compiler
from ceo_voice.core.exceptions import RetrievalBudgetError, RetrievalValidationError
from ceo_voice.models.enums import ContextRole
from ceo_voice.models.retrieval import RetrievedContext, RetrievedItem
from ceo_voice.profiles import PublishedVoiceProfile
from ceo_voice.retrieval import (
    EvidenceMaterial,
    InMemoryEvidenceMaterialReader,
    RetrievalBudget,
    RetrievalBundle,
    RetrievalInput,
    RetrievalIntelligenceEngine,
)
from ceo_voice.retrieval.enums import EvidencePurpose, EvidenceSourceKind
from ceo_voice.utils.hashing import sha256_text
from tests.unit.context.factories import compilation_input
from tests.unit.voice.factories import NOW, TENANT_ID, evidence_unit, observation


def _input(
    *, budget: RetrievalBudget | None = None, with_supplied_evidence: bool = False
) -> tuple[RetrievalInput, tuple[EvidenceMaterial, ...]]:
    retrieved = None
    if with_supplied_evidence:
        retrieved = RetrievedContext(
            trace_id=UUID(int=777),
            query="ownership evidence",
            items=(
                RetrievedItem(
                    document_id=UUID(int=602),
                    content="Internal benchmark confirms ownership reduced cycle time.",
                    role=ContextRole.FACTUAL_EVIDENCE,
                    score=0.91,
                    rank=1,
                ),
            ),
            generated_at=NOW,
        )
    compilation = compilation_input(retrieved_evidence=retrieved)
    context = create_context_compiler().compile(compilation)
    assert compilation.voice_release is not None
    profile = PublishedVoiceProfile.model_construct(
        **cast(
            Any,
            {
                "managed_release": compilation.voice_release,
                "validation_report": compilation.voice_release.validation_report,
                "observations": (observation(),),
                "evidence_units": (evidence_unit(),),
                "inspection": SimpleNamespace(release_id=compilation.voice_release.release.id),
                "retrieval_projection": SimpleNamespace(
                    release_id=compilation.voice_release.release.id,
                    release_content_hash=compilation.voice_release.release.content_hash,
                ),
            },
        )
    )
    materials = []
    voice_ids = {eid for item in context.voice.features for eid in item.evidence_unit_ids}
    structural_ids = {
        eid for item in context.virality.guidance for eid in item.supporting_evidence_ids
    }
    for index, evidence_id in enumerate(
        sorted(voice_ids | structural_ids, key=lambda item: item.int)
    ):
        content = f"Evidence {index} about ownership, execution, and operating leaders."
        materials.append(
            EvidenceMaterial(
                evidence_id=evidence_id,
                tenant_id=TENANT_ID,
                document_id=UUID(int=9000 + index),
                document_version=1,
                content=content,
                content_hash=sha256_text(content),
                source_kind=(
                    EvidenceSourceKind.HVM if evidence_id in voice_ids else EvidenceSourceKind.VKR
                ),
                platform=context.intent.platform,
                publication_time=NOW,
                diversity_cluster_id=f"cluster-{index}",
            )
        )
    return (
        RetrievalInput(
            request=compilation.request,
            context=context,
            voice_profile=profile,
            virality_profile=compilation.virality_profile,
            budget=budget or RetrievalBudget(),
            retrieved_at=NOW + timedelta(days=30),
        ),
        tuple(materials),
    )


def test_engine_builds_compact_explainable_sealed_bundle_deterministically() -> None:
    value, materials = _input(with_supplied_evidence=True)
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(reversed(materials)))

    first = asyncio.run(engine.retrieve(value))
    second = asyncio.run(engine.retrieve(value))

    assert first == second
    assert first.content_hash and first.bundle_id.int
    assert {item.feature_id for item in first.voice_features} == {
        item.feature_id for item in first.observations
    }
    assert {item.feature_id for item in first.voice_features} == {
        item.feature_id for item in first.aggregates
    }
    assert all(item.explanation.requirements for item in first.evidence)
    assert all(item.explanation.source_artifact_ids for item in first.evidence)
    assert first.metadata.deterministic is True
    assert first.metadata.semantic_ranking_used is False
    assert any(item.source_kind is EvidenceSourceKind.REQUEST for item in first.evidence)
    assert any(EvidencePurpose.FACTUAL_SUPPORT in item.purposes for item in first.evidence)
    assert (
        first.metadata.evidence_characters_used <= first.metadata.budget.maximum_evidence_characters
    )
    assert {item.requirement for item in first.report.coverage} >= {
        *(f"voice:{item.feature_id}" for item in first.voice_features),
        *(f"structure:{item.pattern_id}" for item in first.structural_guidance),
    }

    payload = first.model_dump()
    payload["metadata"] = first.metadata.model_copy(
        update={"evidence_items_selected": first.metadata.evidence_items_selected + 1}
    )
    with pytest.raises(ValueError, match="item count"):
        RetrievalBundle(**payload)

    payload = first.model_dump()
    payload["evidence"] = (
        first.evidence[0].model_copy(update={"rank": 2}),
        *first.evidence[1:],
    )
    with pytest.raises(ValueError, match="contiguous"):
        RetrievalBundle(**payload)

    payload = first.model_dump()
    payload["metadata"] = first.metadata.model_copy(
        update={"evidence_characters_used": first.metadata.evidence_characters_used + 1}
    )
    with pytest.raises(ValueError, match="character count"):
        RetrievalBundle(**payload)

    payload = first.model_dump()
    payload["content_hash"] = "0" * 64
    with pytest.raises(ValueError, match="content hash"):
        RetrievalBundle(**payload)

    payload = first.model_dump()
    payload["bundle_id"] = UUID(int=999)
    with pytest.raises(ValueError, match="bundle ID"):
        RetrievalBundle(**payload)


def test_missing_material_fails_closed_instead_of_silently_weakening_coverage() -> None:
    value, _ = _input()
    with pytest.raises(RetrievalValidationError, match="no evidence"):
        asyncio.run(RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(())).retrieve(value))


def test_mandatory_coverage_cannot_overrun_hard_item_budget() -> None:
    value, materials = _input(budget=RetrievalBudget(maximum_evidence_items=1))
    with pytest.raises(RetrievalBudgetError, match="exceeds"):
        asyncio.run(
            RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(value)
        )


def test_cross_platform_request_is_rejected_before_evidence_resolution() -> None:
    value, materials = _input()
    invalid = value.model_copy(
        update={"request": value.request.model_copy(update={"platform": "x"})}
    )
    with pytest.raises(RetrievalValidationError, match="incompatible"):
        asyncio.run(
            RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(invalid)
        )


def test_selected_evidence_must_retain_observation_and_aggregate_support() -> None:
    value, materials = _input()
    unsupported = value.model_copy(
        update={"voice_profile": value.voice_profile.model_copy(update={"observations": ()})}
    )
    with pytest.raises(RetrievalValidationError, match="governed observation"):
        asyncio.run(
            RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(
                unsupported
            )
        )


def test_evidence_material_hash_and_budget_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="hash"):
        EvidenceMaterial(
            evidence_id=UUID(int=1),
            tenant_id=UUID(int=2),
            document_id=UUID(int=3),
            document_version=1,
            content="text",
            content_hash="0" * 64,
            source_kind=EvidenceSourceKind.HVM,
            platform=None,
            publication_time=None,
            diversity_cluster_id="cluster",
        )
    with pytest.raises(ValueError, match="maximum"):
        RetrievalBudget(maximum_items_per_requirement=1, minimum_voice_evidence_per_feature=2)
