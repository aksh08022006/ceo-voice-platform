"""Deterministic knowledge-serving orchestration for one generation context."""

from collections import defaultdict
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue

from ceo_voice.context import VoiceResolutionSource
from ceo_voice.core.exceptions import RetrievalValidationError
from ceo_voice.models.enums import ContextRole
from ceo_voice.retrieval.contracts import (
    AggregateSummary,
    EvidenceMaterial,
    ObservationSummary,
    PreferenceSummary,
    RequirementCoverage,
    RetrievalBundle,
    RetrievalInput,
    RetrievalMetadata,
    RetrievalPolicy,
    RetrievalReport,
    RetrievalTrace,
    RetrievedEvidence,
    SelectionExplanation,
    compute_retrieval_bundle_hash,
    freshness_score,
    retrieval_bundle_id,
)
from ceo_voice.retrieval.enums import EvidencePurpose, EvidenceSourceKind, KnowledgeKind
from ceo_voice.retrieval.ports import EvidenceMaterialReader
from ceo_voice.retrieval.ranking import rerank_candidates
from ceo_voice.retrieval.ranking_contracts import RetrievalRankingMode
from ceo_voice.retrieval.scoring import exact_intent_match, mean, score_evidence
from ceo_voice.retrieval.selection import BudgetedEvidenceSelector, EvidenceCandidate
from ceo_voice.retrieval.validation import validate_retrieval_input
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.voice import PrototypeKind


class RetrievalIntelligenceEngine:
    """Assemble compact evidence from pinned HVM/VKR knowledge and supplied facts."""

    def __init__(
        self, material_reader: EvidenceMaterialReader, *, policy: RetrievalPolicy | None = None
    ) -> None:
        self._reader = material_reader
        self._policy = policy or RetrievalPolicy()
        self._selector = BudgetedEvidenceSelector(
            diversity_bonus=self._policy.diversity_bonus,
            repeated_document_penalty=self._policy.repeated_document_penalty,
        )

    async def retrieve(self, value: RetrievalInput) -> RetrievalBundle:
        """Validate, rank, budget, explain, and seal one reproducible bundle."""

        validate_retrieval_input(value)
        candidates = await self._candidates(value)
        self._validate_candidate_coverage(value, candidates)
        ranking_report = rerank_candidates(
            tuple(candidates.values()),
            topic=value.request.topic,
            tenant_id=value.request.tenant_id,
            ranking=value.ranking,
        )
        result = self._selector.select(
            tuple(candidates.values()),
            budget=value.budget,
            required_requirements=self._required_requirements(value),
        )
        evidence = tuple(
            self._retrieved(candidate, score, rank)
            for rank, (candidate, score) in enumerate(result.selected, start=1)
        )
        coverage = self._coverage(evidence, candidates)
        observations = self._observations(value, {item.evidence_id for item in evidence})
        aggregates = self._aggregates(value, {item.evidence_id for item in evidence})
        if not observations or not aggregates:
            raise RetrievalValidationError(
                "selected voice evidence lacks governed observation or aggregate support",
                details={"reason": "unsupported_features"},
            )
        preferences = self._preferences(value)
        scores = tuple(item.score.final_score for item in evidence)
        release = value.voice_profile.managed_release.release
        traces = [
            RetrievalTrace(
                kind=KnowledgeKind.AGGREGATE,
                identifier=item.aggregate_id,
                parent_identifier=release.id,
            )
            for item in aggregates
        ]
        traces.extend(
            RetrievalTrace(
                kind=KnowledgeKind.OBSERVATION,
                identifier=item.observation_id,
                parent_identifier=release.id,
            )
            for item in observations
        )
        traces.extend(
            RetrievalTrace(
                kind=KnowledgeKind.STRUCTURAL_PATTERN,
                identifier=item.pattern_id,
                parent_identifier=value.virality_profile.publication.release.id,
            )
            for item in value.context.virality.guidance
        )
        report = RetrievalReport(
            coverage=coverage,
            pruned=result.pruned,
            traceability=tuple(
                sorted(traces, key=lambda item: (item.kind.value, item.identifier.int))
            ),
            minimum_selected_score=min(scores),
            mean_selected_score=mean(scores),
            distinct_documents=len({item.document_id for item in evidence}),
            distinct_diversity_clusters=len({item.diversity_cluster_id for item in evidence}),
        )
        metadata = RetrievalMetadata(
            engine_version=self._policy.version,
            retrieved_at=value.retrieved_at,
            candidates_considered=len(candidates),
            evidence_items_selected=len(evidence),
            evidence_items_pruned=len(result.pruned),
            evidence_characters_used=sum(len(item.content) for item in evidence),
            representative_examples_selected=sum(
                EvidencePurpose.REPRESENTATIVE_EXAMPLE in item.purposes for item in evidence
            ),
            budget=value.budget,
            semantic_ranking_used=(
                ranking_report is not None and ranking_report.mode is RetrievalRankingMode.HYBRID
            ),
            ranking_report=ranking_report,
        )
        provisional = RetrievalBundle.model_construct(
            bundle_id=UUID(int=0),
            content_hash="0" * 64,
            source_context_id=value.context.context_id,
            source_context_hash=value.context.content_hash,
            intent=value.context.intent,
            platform=value.context.platform,
            voice_features=value.context.voice.features,
            structural_guidance=value.context.virality.guidance,
            constraints=value.context.constraints,
            observations=observations,
            aggregates=aggregates,
            preferences=preferences,
            evidence=evidence,
            report=report,
            metadata=metadata,
        )
        digest = compute_retrieval_bundle_hash(provisional)
        return RetrievalBundle(
            **provisional.model_dump(exclude={"bundle_id", "content_hash"}),
            content_hash=digest,
            bundle_id=retrieval_bundle_id(digest),
        )

    async def candidate_materials(self, value: RetrievalInput) -> tuple[EvidenceMaterial, ...]:
        """Expose exact eligible spans for an external embedding preparer, without ranking."""

        validate_retrieval_input(value)
        candidates = await self._candidates(value)
        self._validate_candidate_coverage(value, candidates)
        return tuple(
            item.material
            for item in sorted(candidates.values(), key=lambda item: item.material.evidence_id.int)
        )

    @classmethod
    def _validate_candidate_coverage(
        cls, value: RetrievalInput, candidates: dict[UUID, EvidenceCandidate]
    ) -> None:
        if not candidates:
            raise RetrievalValidationError(
                "retrieval produced no evidence candidates",
                details={"reason": "missing_required_evidence"},
            )
        for requirement, kind in cls._required_requirements(value).items():
            minimum = (
                value.budget.minimum_voice_evidence_per_feature
                if kind is KnowledgeKind.VOICE_FEATURE
                else (
                    value.budget.minimum_structural_evidence_per_pattern
                    if kind is KnowledgeKind.STRUCTURAL_PATTERN
                    else 1
                )
            )
            available = sum(requirement in item.requirements for item in candidates.values())
            if available < minimum:
                raise RetrievalValidationError(
                    "mandatory retrieval requirement lacks evidence",
                    details={"reason": "missing_required_evidence", "requirement": requirement},
                )

    @staticmethod
    def _required_requirements(value: RetrievalInput) -> dict[str, KnowledgeKind]:
        """Requirements come from governed targets, never from surviving material."""

        return {
            **{
                f"voice:{item.feature_id}": KnowledgeKind.VOICE_FEATURE
                for item in value.context.voice.features
            },
            **{
                f"structure:{item.pattern_id}": KnowledgeKind.STRUCTURAL_PATTERN
                for item in value.context.virality.guidance
            },
            **{
                f"request:{lane.role.value}": KnowledgeKind.PLATFORM_POLICY
                for lane in value.context.evidence.lanes
                if lane.items
            },
        }

    async def _candidates(self, value: RetrievalInput) -> dict[UUID, EvidenceCandidate]:
        release = value.voice_profile.managed_release.release
        voice_features = {item.feature_id: item for item in value.context.voice.features}
        structural = {item.pattern_id: item for item in value.context.virality.guidance}
        wanted: set[UUID] = set()
        links: dict[
            UUID, list[tuple[str, KnowledgeKind, EvidencePurpose, str, UUID, float, int]]
        ] = defaultdict(list)
        for feature in voice_features.values():
            requirement = f"voice:{feature.feature_id}"
            for evidence_id in feature.evidence_unit_ids:
                wanted.add(evidence_id)
                links[evidence_id].append(
                    (
                        requirement,
                        KnowledgeKind.VOICE_FEATURE,
                        EvidencePurpose.VOICE_SUPPORT,
                        feature.feature_id,
                        feature.component_ids[0],
                        feature.confidence.selection_score,
                        80,
                    )
                )
        for prototype in release.prototypes:
            feature_ids = {
                item.feature_id for item in prototype.represented_features
            } & voice_features.keys()
            if not feature_ids:
                continue
            wanted.add(prototype.evidence_unit_id)
            purpose = (
                EvidencePurpose.REPRESENTATIVE_EXAMPLE
                if prototype.kind is PrototypeKind.PROTOTYPE
                else EvidencePurpose.COUNTEREXAMPLE
            )
            for feature_id in feature_ids:
                links[prototype.evidence_unit_id].append(
                    (
                        f"voice:{feature_id}",
                        KnowledgeKind.VOICE_FEATURE,
                        purpose,
                        feature_id,
                        prototype.id,
                        prototype.representativeness,
                        90,
                    )
                )
        for guidance in structural.values():
            for evidence_id in guidance.supporting_evidence_ids:
                wanted.add(evidence_id)
                links[evidence_id].append(
                    (
                        f"structure:{guidance.pattern_id}",
                        KnowledgeKind.STRUCTURAL_PATTERN,
                        EvidencePurpose.STRUCTURAL_SUPPORT,
                        guidance.feature_id,
                        guidance.pattern_id,
                        guidance.comparable_fraction,
                        75,
                    )
                )
        materials: dict[UUID, EvidenceMaterial] = {}
        for item in await self._reader.get_many(
            value.request.tenant_id, tuple(sorted(wanted, key=lambda item: item.int))
        ):
            if item.tenant_id != value.request.tenant_id or item.evidence_id not in wanted:
                raise RetrievalValidationError(
                    "material reader returned evidence outside the requested ownership boundary",
                    details={"reason": "material_boundary_mismatch"},
                )
            if item.evidence_id in materials:
                raise RetrievalValidationError(
                    "material reader returned a duplicate evidence identifier",
                    details={"reason": "duplicate_evidence_material"},
                )
            materials[item.evidence_id] = item
        candidates: dict[UUID, EvidenceCandidate] = {}
        for evidence_id, contributions in links.items():
            material = materials.get(evidence_id)
            if material is None:
                continue
            if material.platform not in (None, value.request.platform):
                continue
            for (
                requirement,
                kind,
                purpose,
                feature_id,
                artifact_id,
                authority,
                priority,
            ) in contributions:
                confidence = (
                    voice_features[feature_id].confidence.selection_score
                    if kind is KnowledgeKind.VOICE_FEATURE
                    else authority
                )
                score = score_evidence(
                    confidence=confidence,
                    coverage=confidence,
                    freshness=freshness_score(
                        material.publication_time,
                        now=value.retrieved_at,
                        horizon_days=self._policy.freshness_horizon_days,
                    ),
                    platform_match=1.0 if material.platform is value.request.platform else 0.65,
                    feature_importance=(
                        1 / max(1, voice_features[feature_id].rank)
                        if feature_id in voice_features
                        else 0.75
                    ),
                    representativeness=authority,
                    profile_authority=0.9,
                    intent_match=exact_intent_match(material.content, value.context.intent),
                )
                candidate = EvidenceCandidate(
                    material=material,
                    score=score,
                    priority=priority,
                    purposes={purpose},
                    requirements={requirement: kind},
                    feature_ids={feature_id} if kind is KnowledgeKind.VOICE_FEATURE else set(),
                    pattern_ids=(
                        {artifact_id} if kind is KnowledgeKind.STRUCTURAL_PATTERN else set()
                    ),
                    artifact_ids={artifact_id},
                    reasons={f"supports {requirement}"},
                    generation_uses={"govern the corresponding generation decision"},
                )
                if evidence_id in candidates:
                    candidates[evidence_id].merge(candidate)
                else:
                    candidates[evidence_id] = candidate
        self._add_supplied_evidence(value, candidates)
        return candidates

    @staticmethod
    def _add_supplied_evidence(
        value: RetrievalInput, candidates: dict[UUID, EvidenceCandidate]
    ) -> None:
        for lane in value.context.evidence.lanes:
            for item in lane.items:
                evidence_id = uuid5(
                    NAMESPACE_URL,
                    f"request-evidence:{value.context.context_id}:{lane.role}:{item.document_id}:{item.rank}:{sha256_text(item.content)}",
                )
                material = EvidenceMaterial(
                    evidence_id=evidence_id,
                    tenant_id=value.request.tenant_id,
                    document_id=item.document_id,
                    document_version=1,
                    content=item.content,
                    content_hash=sha256_text(item.content),
                    source_kind=EvidenceSourceKind.REQUEST,
                    platform=value.request.platform,
                    publication_time=None,
                    diversity_cluster_id=f"request:{item.document_id}",
                )
                purpose = (
                    EvidencePurpose.FACTUAL_SUPPORT
                    if lane.role is ContextRole.FACTUAL_EVIDENCE
                    else EvidencePurpose.PLATFORM_REFERENCE
                )
                requirement = f"request:{lane.role.value}"
                score = score_evidence(
                    confidence=max(0, min(1, item.score)),
                    coverage=1,
                    freshness=0.5,
                    platform_match=1,
                    feature_importance=0.7,
                    representativeness=0.7,
                    profile_authority=1,
                    intent_match=exact_intent_match(item.content, value.context.intent),
                )
                candidates[evidence_id] = EvidenceCandidate(
                    material=material,
                    score=score,
                    priority=85,
                    purposes={purpose},
                    requirements={requirement: KnowledgeKind.PLATFORM_POLICY},
                    artifact_ids={value.context.context_id},
                    reasons={f"supplied {lane.role.value} evidence"},
                    generation_uses={"ground the requested content"},
                )

    @staticmethod
    def _retrieved(candidate: EvidenceCandidate, score: object, rank: int) -> RetrievedEvidence:
        from ceo_voice.retrieval.contracts import RetrievalScore

        resolved = cast(RetrievalScore, score)
        return RetrievedEvidence(
            evidence_id=candidate.material.evidence_id,
            document_id=candidate.material.document_id,
            content=candidate.material.content,
            content_hash=candidate.material.content_hash,
            source_kind=candidate.material.source_kind,
            platform=candidate.material.platform,
            publication_time=candidate.material.publication_time,
            diversity_cluster_id=candidate.material.diversity_cluster_id,
            purposes=tuple(sorted(candidate.purposes, key=lambda item: item.value)),
            rank=rank,
            priority=candidate.priority,
            score=resolved,
            explanation=SelectionExplanation(
                reason="; ".join(sorted(candidate.reasons)),
                generation_use="; ".join(sorted(candidate.generation_uses)),
                requirements=tuple(sorted(candidate.requirements)),
                supporting_feature_ids=tuple(sorted(candidate.feature_ids)),
                supporting_pattern_ids=tuple(
                    sorted(candidate.pattern_ids, key=lambda item: item.int)
                ),
                source_artifact_ids=tuple(
                    sorted(candidate.artifact_ids, key=lambda item: item.int)
                ),
            ),
        )

    @staticmethod
    def _coverage(
        evidence: tuple[RetrievedEvidence, ...], candidates: dict[UUID, EvidenceCandidate]
    ) -> tuple[RequirementCoverage, ...]:
        grouped: dict[str, tuple[KnowledgeKind, list[UUID]]] = {}
        for item in evidence:
            for requirement, kind in candidates[item.evidence_id].requirements.items():
                grouped.setdefault(requirement, (kind, []))[1].append(item.evidence_id)
        return tuple(
            RequirementCoverage(
                requirement=key, kind=value[0], selected_evidence_ids=tuple(value[1])
            )
            for key, value in sorted(grouped.items())
        )

    def _observations(
        self, value: RetrievalInput, selected: set[UUID]
    ) -> tuple[ObservationSummary, ...]:
        feature_ids = {item.feature_id for item in value.context.voice.features}
        result = []
        for item in value.voice_profile.observations:
            evidence_ids = tuple(
                ref.evidence_unit_id for ref in item.evidence if ref.evidence_unit_id in selected
            )
            if (
                item.feature.feature_id in feature_ids
                and evidence_ids
                and item.value is not None
                and item.quality >= self._policy.minimum_observation_quality
            ):
                result.append(
                    ObservationSummary(
                        observation_id=item.id,
                        feature_id=item.feature.feature_id,
                        value=cast(JsonValue, item.value.model_dump(mode="json")),
                        quality=item.quality,
                        measurement_class=item.measurement_class.value,
                        event_time=item.event_time,
                        evidence_ids=evidence_ids,
                        selection_reason="high-quality observation supports a selected voice feature",
                    )
                )
        return tuple(sorted(result, key=lambda item: (-item.quality, item.observation_id.int)))

    @staticmethod
    def _aggregates(value: RetrievalInput, selected: set[UUID]) -> tuple[AggregateSummary, ...]:
        feature_ids = {item.feature_id for item in value.context.voice.features}
        result = []
        for item in value.voice_profile.managed_release.release.components.aggregates:
            evidence_ids = tuple(eid for eid in item.evidence_unit_ids if eid in selected)
            if item.feature.feature_id in feature_ids and evidence_ids:
                result.append(
                    AggregateSummary(
                        aggregate_id=item.id,
                        feature_id=item.feature.feature_id,
                        value=cast(JsonValue, item.value.model_dump(mode="json")),
                        platform=item.context.platform,
                        decision_state=item.decision_state,
                        coverage=item.confidence.coverage,
                        effective_support=item.confidence.effective_support,
                        evidence_ids=evidence_ids,
                    )
                )
        return tuple(sorted(result, key=lambda item: (item.feature_id, item.aggregate_id.int)))

    @staticmethod
    def _preferences(value: RetrievalInput) -> tuple[PreferenceSummary, ...]:
        selected = {
            item.feature_id
            for item in value.context.voice.features
            if item.resolution_source is VoiceResolutionSource.EXPLICIT_PREFERENCE
        }
        return tuple(
            PreferenceSummary(
                preference_id=item.id,
                feature_id=item.feature.feature_id,
                target=cast(JsonValue, item.target.model_dump(mode="json")),
                priority=item.priority,
                authority=item.authority.value,
                rationale_category=item.rationale_category,
            )
            for item in value.voice_profile.managed_release.release.explicit_preferences
            if item.feature.feature_id in selected
        )
