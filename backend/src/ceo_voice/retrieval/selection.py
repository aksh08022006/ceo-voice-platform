"""Diversity-aware mandatory coverage and deterministic context budgeting."""

from dataclasses import dataclass, field
from uuid import UUID

from ceo_voice.core.exceptions import RetrievalBudgetError, RetrievalValidationError
from ceo_voice.retrieval.contracts import (
    EvidenceMaterial,
    PrunedCandidate,
    RetrievalBudget,
    RetrievalScore,
)
from ceo_voice.retrieval.enums import (
    EvidencePurpose,
    KnowledgeKind,
    RetrievalPruneReason,
)


@dataclass
class EvidenceCandidate:
    """Mutable internal accumulator; it never crosses the retrieval boundary."""

    material: EvidenceMaterial
    score: RetrievalScore
    priority: int
    purposes: set[EvidencePurpose] = field(default_factory=set)
    requirements: dict[str, KnowledgeKind] = field(default_factory=dict)
    feature_ids: set[str] = field(default_factory=set)
    pattern_ids: set[UUID] = field(default_factory=set)
    artifact_ids: set[UUID] = field(default_factory=set)
    reasons: set[str] = field(default_factory=set)
    generation_uses: set[str] = field(default_factory=set)

    def merge(self, other: "EvidenceCandidate") -> None:
        """Merge duplicate evidence contributions without duplicating content."""

        if self.material != other.material:
            raise RetrievalValidationError(
                "one evidence identifier resolved to conflicting material",
                details={
                    "reason": "evidence_identity_conflict",
                    "evidence_id": str(self.material.evidence_id),
                },
            )
        if other.score.base_score > self.score.base_score:
            self.score = other.score
        self.priority = max(self.priority, other.priority)
        self.purposes.update(other.purposes)
        self.requirements.update(other.requirements)
        self.feature_ids.update(other.feature_ids)
        self.pattern_ids.update(other.pattern_ids)
        self.artifact_ids.update(other.artifact_ids)
        self.reasons.update(other.reasons)
        self.generation_uses.update(other.generation_uses)


@dataclass(frozen=True)
class SelectionResult:
    """Selected candidates, their adjusted scores, and explicit pruning decisions."""

    selected: tuple[tuple[EvidenceCandidate, RetrievalScore], ...]
    pruned: tuple[PrunedCandidate, ...]


class BudgetedEvidenceSelector:
    """Cover mandatory requirements first, then maximize density and diversity."""

    def __init__(self, *, diversity_bonus: float, repeated_document_penalty: float) -> None:
        self._diversity_bonus = diversity_bonus
        self._repeated_document_penalty = repeated_document_penalty

    def select(
        self,
        candidates: tuple[EvidenceCandidate, ...],
        *,
        budget: RetrievalBudget,
        required_requirements: dict[str, KnowledgeKind] | None = None,
    ) -> SelectionResult:
        """Select a deterministic set that never exceeds any configured hard budget."""

        if not candidates:
            raise RetrievalValidationError(
                "retrieval produced no evidence candidates",
                details={"reason": "missing_required_evidence"},
            )
        requirements = self._requirements(candidates)
        if required_requirements is not None:
            for requirement, kind in required_requirements.items():
                if requirement not in requirements:
                    raise RetrievalValidationError(
                        "mandatory retrieval requirement lacks evidence",
                        details={"reason": "missing_required_evidence", "requirement": requirement},
                    )
                if requirements[requirement] is not kind:
                    raise RetrievalValidationError(
                        "mandatory retrieval requirement has the wrong knowledge kind",
                        details={"reason": "requirement_conflict", "requirement": requirement},
                    )
        selected: list[tuple[EvidenceCandidate, RetrievalScore]] = []
        selected_ids: set[UUID] = set()
        counts: dict[str, int] = dict.fromkeys(requirements, 0)

        for requirement, kind in sorted(requirements.items()):
            minimum = self._minimum(kind, budget)
            while counts[requirement] < minimum:
                choices = tuple(
                    item
                    for item in candidates
                    if requirement in item.requirements
                    and item.material.evidence_id not in selected_ids
                )
                if not choices:
                    raise RetrievalValidationError(
                        "mandatory retrieval requirement lacks evidence",
                        details={"reason": "missing_required_evidence", "requirement": requirement},
                    )
                ranked = self._rank(choices, selected)
                admissible = next(
                    (
                        pair
                        for pair in ranked
                        if self._budget_violation(pair[0], selected, budget, counts) is None
                    ),
                    None,
                )
                if admissible is None:
                    violation = self._budget_violation(ranked[0][0], selected, budget, counts)
                    raise RetrievalBudgetError(
                        "mandatory retrieval evidence exceeds the configured budget",
                        details={
                            "reason": violation.value if violation else "no_admissible_candidate",
                            "requirement": requirement,
                        },
                    )
                choice, adjusted = admissible
                self._append(choice, adjusted, selected, selected_ids, counts)

        remaining = tuple(
            item for item in candidates if item.material.evidence_id not in selected_ids
        )
        pruned: list[PrunedCandidate] = []
        while remaining:
            candidate, adjusted = self._rank(remaining, selected)[0]
            remaining = tuple(
                item
                for item in remaining
                if item.material.evidence_id != candidate.material.evidence_id
            )
            violation = self._budget_violation(candidate, selected, budget, counts)
            if violation is not None:
                pruned.append(self._pruned(candidate, violation))
                continue
            self._append(candidate, adjusted, selected, selected_ids, counts)

        selected.sort(
            key=lambda item: (
                -item[1].final_score,
                -item[0].priority,
                item[0].material.evidence_id.int,
            )
        )
        pruned.extend(
            self._pruned(candidate, RetrievalPruneReason.LOWER_RANK)
            for candidate in candidates
            if candidate.material.evidence_id not in selected_ids
            and all(item.evidence_id != candidate.material.evidence_id for item in pruned)
        )
        return SelectionResult(
            selected=tuple(selected),
            pruned=tuple(sorted(pruned, key=lambda item: item.evidence_id.int)),
        )

    def _rank(
        self,
        candidates: tuple[EvidenceCandidate, ...],
        selected: list[tuple[EvidenceCandidate, RetrievalScore]],
    ) -> tuple[tuple[EvidenceCandidate, RetrievalScore], ...]:
        documents = {item.material.document_id for item, _ in selected}
        clusters = {item.material.diversity_cluster_id for item, _ in selected}
        ranked: list[tuple[EvidenceCandidate, RetrievalScore]] = []
        for candidate in candidates:
            adjustment = 0.0
            if candidate.material.diversity_cluster_id not in clusters:
                adjustment += self._diversity_bonus
            if candidate.material.document_id in documents:
                adjustment -= self._repeated_document_penalty
            final = min(1.0, max(0.0, candidate.score.base_score + adjustment))
            score = candidate.score.model_copy(
                update={
                    "diversity_adjustment": round(adjustment, 6),
                    "final_score": round(final, 6),
                }
            )
            ranked.append((candidate, score))
        return tuple(
            sorted(
                ranked,
                key=lambda item: (
                    -item[1].final_score,
                    -item[0].priority,
                    item[0].material.evidence_id.int,
                ),
            )
        )

    @staticmethod
    def _append(
        candidate: EvidenceCandidate,
        score: RetrievalScore,
        selected: list[tuple[EvidenceCandidate, RetrievalScore]],
        selected_ids: set[UUID],
        counts: dict[str, int],
    ) -> None:
        selected.append((candidate, score))
        selected_ids.add(candidate.material.evidence_id)
        for requirement in candidate.requirements:
            counts[requirement] += 1

    @staticmethod
    def _requirements(candidates: tuple[EvidenceCandidate, ...]) -> dict[str, KnowledgeKind]:
        requirements: dict[str, KnowledgeKind] = {}
        for candidate in candidates:
            for key, kind in candidate.requirements.items():
                existing = requirements.get(key)
                if existing is not None and existing is not kind:
                    raise RetrievalValidationError(
                        "retrieval requirement has conflicting knowledge kinds",
                        details={"reason": "requirement_conflict", "requirement": key},
                    )
                requirements[key] = kind
        return requirements

    @staticmethod
    def _minimum(kind: KnowledgeKind, budget: RetrievalBudget) -> int:
        if kind is KnowledgeKind.VOICE_FEATURE:
            return budget.minimum_voice_evidence_per_feature
        if kind is KnowledgeKind.STRUCTURAL_PATTERN:
            return budget.minimum_structural_evidence_per_pattern
        return 1

    @staticmethod
    def _budget_violation(
        candidate: EvidenceCandidate,
        selected: list[tuple[EvidenceCandidate, RetrievalScore]],
        budget: RetrievalBudget,
        counts: dict[str, int],
    ) -> RetrievalPruneReason | None:
        if len(selected) >= budget.maximum_evidence_items:
            return RetrievalPruneReason.ITEM_BUDGET
        used_characters = sum(len(item.material.content) for item, _ in selected)
        if used_characters + len(candidate.material.content) > budget.maximum_evidence_characters:
            return RetrievalPruneReason.CHARACTER_BUDGET
        selected_examples = sum(
            EvidencePurpose.REPRESENTATIVE_EXAMPLE in item.purposes for item, _ in selected
        )
        if (
            EvidencePurpose.REPRESENTATIVE_EXAMPLE in candidate.purposes
            and selected_examples >= budget.maximum_representative_examples
        ):
            return RetrievalPruneReason.EXAMPLE_BUDGET
        if any(
            counts[requirement] >= budget.maximum_items_per_requirement
            for requirement in candidate.requirements
        ):
            return RetrievalPruneReason.PER_REQUIREMENT_BUDGET
        return None

    @staticmethod
    def _pruned(candidate: EvidenceCandidate, reason: RetrievalPruneReason) -> PrunedCandidate:
        return PrunedCandidate(
            evidence_id=candidate.material.evidence_id,
            reason=reason,
            base_score=candidate.score.base_score,
            requirements=tuple(sorted(candidate.requirements)),
        )
