"""Missing coverage, ownership, fitting alternatives and adaptive-diversity regressions."""

import asyncio
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import RetrievalBudgetError, RetrievalValidationError
from ceo_voice.retrieval import (
    EvidenceMaterial,
    InMemoryEvidenceMaterialReader,
    RetrievalBudget,
    RetrievalIntelligenceEngine,
)
from ceo_voice.retrieval.enums import EvidencePurpose, EvidenceSourceKind, KnowledgeKind
from ceo_voice.retrieval.selection import BudgetedEvidenceSelector
from tests.unit.retrieval.test_engine import _input
from tests.unit.retrieval.test_ranking import _candidate


def test_missing_structural_material_cannot_erase_mandatory_requirements() -> None:
    value, materials = _input()
    voice_only = tuple(item for item in materials if item.source_kind is EvidenceSourceKind.HVM)
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(voice_only))
    for operation in (engine.candidate_materials, engine.retrieve):
        with pytest.raises(RetrievalValidationError, match="mandatory") as caught:
            asyncio.run(operation(value))
        assert str(caught.value.details["requirement"]).startswith("structure:")


def test_missing_voice_evidence_is_rejected_before_optional_embedding_preparation() -> None:
    value, materials = _input()
    structural_only = tuple(
        item for item in materials if item.source_kind is EvidenceSourceKind.VKR
    )
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(structural_only))
    with pytest.raises(RetrievalValidationError, match="mandatory") as caught:
        asyncio.run(engine.candidate_materials(value))
    assert str(caught.value.details["requirement"]).startswith("voice:")


def test_reader_results_are_revalidated_at_the_ownership_boundary() -> None:
    value, materials = _input()

    class UntrustedReader:
        def __init__(self, returned: tuple[EvidenceMaterial, ...]) -> None:
            self.returned = returned

        async def get_many(
            self, tenant_id: UUID, evidence_ids: tuple[UUID, ...]
        ) -> tuple[EvidenceMaterial, ...]:
            return self.returned

    for bad, reason in (
        (
            (materials[0].model_copy(update={"tenant_id": UUID(int=981)}),),
            "material_boundary_mismatch",
        ),
        (
            (materials[0].model_copy(update={"evidence_id": UUID(int=982)}),),
            "material_boundary_mismatch",
        ),
        ((materials[0], materials[0]), "duplicate_evidence_material"),
    ):
        with pytest.raises(RetrievalValidationError) as caught:
            asyncio.run(RetrievalIntelligenceEngine(UntrustedReader(bad)).retrieve(value))
        assert caught.value.details["reason"] == reason


def test_mandatory_selection_tries_lower_ranked_evidence_that_fits() -> None:
    expensive = _candidate(1, "long high-authority evidence " * 10, authority=0.9)
    affordable = _candidate(2, "brief", authority=0.7)
    selector = BudgetedEvidenceSelector(diversity_bonus=0.05, repeated_document_penalty=0.08)
    result = selector.select(
        (expensive, affordable),
        budget=RetrievalBudget(maximum_evidence_characters=10),
    )
    assert tuple(item.material.evidence_id for item, _ in result.selected) == (UUID(int=2),)
    assert result.pruned[0].evidence_id == UUID(int=1)


def test_optional_diversity_is_updated_after_each_selected_document() -> None:
    first = _candidate(1, "first", authority=0.9)
    second = _candidate(2, "second", authority=0.8)
    duplicate = _candidate(3, "another span from the second document", authority=0.79)
    duplicate.material = duplicate.material.model_copy(
        update={
            "document_id": second.material.document_id,
            "diversity_cluster_id": second.material.diversity_cluster_id,
        }
    )
    diverse = _candidate(4, "new document", authority=0.75)
    result = BudgetedEvidenceSelector(diversity_bonus=0.05, repeated_document_penalty=0.08).select(
        (first, second, duplicate, diverse),
        budget=RetrievalBudget(maximum_evidence_items=3, maximum_items_per_requirement=3),
    )
    assert {item.material.evidence_id for item, _ in result.selected} == {
        UUID(int=1),
        UUID(int=2),
        UUID(int=4),
    }


def test_selector_checks_the_explicit_requirement_set_and_kind() -> None:
    candidate = _candidate(1, "voice")
    selector = BudgetedEvidenceSelector(diversity_bonus=0, repeated_document_penalty=0)
    for required in (
        {"missing": KnowledgeKind.STRUCTURAL_PATTERN},
        {"voice:test-feature": KnowledgeKind.STRUCTURAL_PATTERN},
    ):
        with pytest.raises(RetrievalValidationError, match="mandatory"):
            selector.select((candidate,), budget=RetrievalBudget(), required_requirements=required)


def test_mandatory_example_limit_can_choose_a_nonexample_alternative() -> None:
    example = _candidate(1, "example", authority=0.9)
    example.purposes.add(EvidencePurpose.REPRESENTATIVE_EXAMPLE)
    support = _candidate(2, "support", authority=0.7)
    selector = BudgetedEvidenceSelector(diversity_bonus=0, repeated_document_penalty=0)
    result = selector.select(
        (example, support), budget=RetrievalBudget(maximum_representative_examples=0)
    )
    assert result.selected[0][0].material.evidence_id == support.material.evidence_id
    with pytest.raises(RetrievalBudgetError, match="exceeds"):
        selector.select((example,), budget=RetrievalBudget(maximum_representative_examples=0))
