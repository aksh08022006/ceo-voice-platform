"""Deterministic orchestration from governed knowledge releases to GenerationContext."""

from uuid import UUID

from ceo_voice.context.constraints import ConstraintCompiler
from ceo_voice.context.contracts import (
    CompilationInput,
    CompilationReport,
    CompiledVoiceFeature,
    CompiledVoiceInteraction,
    ConfidenceSummary,
    ContextCompilationPolicy,
    GenerationContext,
    GenerationIntent,
    StructuralGuidance,
    TraceReference,
    compute_generation_context_hash,
    generation_context_id,
)
from ceo_voice.context.enums import TraceArtifactKind
from ceo_voice.context.evidence import EvidenceCompiler
from ceo_voice.context.platforms import PlatformContractCatalog
from ceo_voice.context.structure import ViralityCompiler
from ceo_voice.context.voice import VoiceCompiler
from ceo_voice.core.exceptions import ContextCompilationError
from ceo_voice.virality.contracts import ViralityProfile
from ceo_voice.virality.enums import PublicationStatus
from ceo_voice.voice.enums import ReleaseStatus
from ceo_voice.voice.releases import ManagedRelease


class ContextCompiler:
    """Build the sole model-neutral input permitted for future generation adapters."""

    def __init__(
        self,
        *,
        platform_catalog: PlatformContractCatalog,
        policy: ContextCompilationPolicy | None = None,
        constraint_compiler: ConstraintCompiler | None = None,
    ) -> None:
        self._platform_catalog = platform_catalog
        self._policy = policy or ContextCompilationPolicy()
        self._constraint_compiler = constraint_compiler or ConstraintCompiler()
        self._evidence_compiler = EvidenceCompiler()

    def compile(self, compilation: CompilationInput) -> GenerationContext:
        """Validate pinned artifacts, compile independent targets, and seal the context."""

        voice_record, virality_profile = self._validate_inputs(compilation)
        request = compilation.request
        platform_contract = self._platform_catalog.get(request.platform)
        voice_result = VoiceCompiler(
            registry=compilation.feature_registry,
            thresholds=self._policy.confidence,
            maximum_features=self._policy.maximum_voice_features,
        ).compile(
            voice_record.release,
            leader_id=compilation.target_identity.leader_id,
            platform=request.platform,
            language=compilation.language,
            audience=request.audience,
            compiled_at=compilation.compiled_at,
        )
        structure_result = ViralityCompiler(policy=self._policy.structure).compile(
            virality_profile,
            platform=request.platform,
            influence=request.virality_influence,
        )
        constraints = self._constraint_compiler.compile(
            voice_record.release,
            platform_contract=platform_contract,
            language=compilation.language,
            audience=request.audience,
            request_constraints=request.constraints,
            user_constraints=compilation.user_constraints,
            compiled_at=compilation.compiled_at,
        )
        evidence = self._evidence_compiler.compile(
            compilation.retrieved_evidence,
            allowed_factual_document_ids=request.source_document_ids,
        )
        intent = GenerationIntent(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            leader_id=request.ceo_id,
            topic=request.topic,
            objective=request.objective,
            audience=request.audience,
            platform=request.platform,
            content_type=request.content_type,
            thread_post_count=request.thread_post_count,
            minimum_words=request.minimum_words,
            maximum_words=request.maximum_words,
            comment_context=request.comment_context,
            candidate_count=request.candidate_count,
            source_document_ids=request.source_document_ids,
        )
        report = CompilationReport(
            selected_voice_feature_ids=tuple(
                item.feature_id for item in voice_result.target.features
            ),
            ignored_voice=voice_result.ignored,
            selected_structural_pattern_ids=tuple(
                item.pattern_id for item in structure_result.target.guidance
            ),
            ignored_structure=structure_result.ignored,
            constraint_summary=constraints.summary,
            confidence_summary=self._confidence_summary(
                voice_result.target.features,
                structure_result.target.guidance,
            ),
            traceability=self._traceability(
                voice_record.release.id,
                voice_result.target.features,
                voice_result.target.interactions,
                structure_result.target.release_id,
                structure_result.target.guidance,
                (
                    compilation.retrieved_evidence.trace_id
                    if compilation.retrieved_evidence is not None
                    else None
                ),
            ),
        )
        content_hash = compute_generation_context_hash(
            compiler_version=self._policy.compiler_version,
            compiled_at=compilation.compiled_at,
            intent=intent,
            platform=platform_contract,
            voice=voice_result.target,
            virality=structure_result.target,
            constraints=constraints,
            evidence=evidence,
            report=report,
        )
        return GenerationContext(
            context_id=generation_context_id(content_hash),
            content_hash=content_hash,
            compiler_version=self._policy.compiler_version,
            compiled_at=compilation.compiled_at,
            intent=intent,
            platform=platform_contract,
            voice=voice_result.target,
            virality=structure_result.target,
            constraints=constraints,
            evidence=evidence,
            report=report,
        )

    def _validate_inputs(
        self, compilation: CompilationInput
    ) -> tuple[ManagedRelease, ViralityProfile]:
        request = compilation.request
        voice_record = compilation.voice_release
        if voice_record is None:
            raise ContextCompilationError(
                "published HVM release is required",
                details={"reason": "missing_voice_profile"},
            )
        virality_profile = compilation.virality_profile
        if virality_profile is None:
            raise ContextCompilationError(
                "published VKR release is required",
                details={"reason": "missing_virality_profile"},
            )
        identity = compilation.target_identity
        release = voice_record.release
        virality_release = virality_profile.publication.release
        if voice_record.status is not ReleaseStatus.ACTIVE:
            raise ContextCompilationError(
                "HVM release must be active",
                details={"reason": "inactive_voice_profile", "release_id": str(release.id)},
            )
        if voice_record.validation_report is None or not voice_record.validation_report.is_valid():
            raise ContextCompilationError(
                "HVM release requires a successful pinned validation report",
                details={"reason": "invalid_voice_profile", "release_id": str(release.id)},
            )
        if virality_profile.publication.status is not PublicationStatus.ACTIVE:
            raise ContextCompilationError(
                "VKR release must be active",
                details={
                    "reason": "inactive_virality_profile",
                    "release_id": str(virality_release.id),
                },
            )
        if not virality_profile.publication.validation.is_valid():
            raise ContextCompilationError(
                "VKR release requires a successful validation report",
                details={"reason": "invalid_virality_profile"},
            )
        if not (
            request.tenant_id
            == identity.tenant_id
            == release.tenant_id
            == virality_release.tenant_id
        ):
            raise ContextCompilationError(
                "generation artifacts cross tenant boundaries",
                details={"reason": "ownership_mismatch"},
            )
        if identity.id != release.voice_identity_id or identity.leader_id != request.ceo_id:
            raise ContextCompilationError(
                "target identity does not match the HVM release and generation request",
                details={"reason": "identity_mismatch"},
            )
        if request.voice_profile_id != release.lineage_id:
            raise ContextCompilationError(
                "generation request references a different HVM lineage",
                details={"reason": "voice_profile_mismatch"},
            )
        if request.voice_profile_version != release.version:
            raise ContextCompilationError(
                "generation request references a different HVM version",
                details={"reason": "voice_profile_version_mismatch"},
            )
        if compilation.feature_registry.reference != release.registry:
            raise ContextCompilationError(
                "feature registry does not match the HVM release",
                details={"reason": "registry_mismatch"},
            )
        self._platform_catalog.get(request.platform)
        return voice_record, virality_profile

    @staticmethod
    def _confidence_summary(
        features: tuple[CompiledVoiceFeature, ...],
        guidance: tuple[StructuralGuidance, ...],
    ) -> ConfidenceSummary:
        scores = tuple(feature.confidence.selection_score for feature in features)
        supports = tuple(pattern.support_count for pattern in guidance)
        return ConfidenceSummary(
            selected_voice_features=len(scores),
            minimum_voice_score=min(scores) if scores else None,
            mean_voice_score=round(sum(scores) / len(scores), 6) if scores else None,
            selected_structural_patterns=len(supports),
            minimum_structural_support=min(supports) if supports else None,
        )

    @staticmethod
    def _traceability(
        voice_release_id: UUID,
        features: tuple[CompiledVoiceFeature, ...],
        interactions: tuple[CompiledVoiceInteraction, ...],
        virality_release_id: UUID,
        guidance: tuple[StructuralGuidance, ...],
        retrieval_trace_id: UUID | None,
    ) -> tuple[TraceReference, ...]:
        traces = {
            TraceReference(kind=TraceArtifactKind.HVM_RELEASE, identifier=voice_release_id),
            TraceReference(kind=TraceArtifactKind.VKR_RELEASE, identifier=virality_release_id),
        }
        for feature in features:
            traces.update(
                TraceReference(
                    kind=TraceArtifactKind.HVM_COMPONENT,
                    identifier=component_id,
                    parent_identifier=voice_release_id,
                )
                for component_id in feature.component_ids
            )
            traces.update(
                TraceReference(
                    kind=TraceArtifactKind.HVM_EVIDENCE,
                    identifier=evidence_id,
                    parent_identifier=voice_release_id,
                )
                for evidence_id in feature.evidence_unit_ids
            )
        for interaction in interactions:
            traces.add(
                TraceReference(
                    kind=TraceArtifactKind.HVM_COMPONENT,
                    identifier=interaction.interaction_id,
                    parent_identifier=voice_release_id,
                )
            )
            traces.update(
                TraceReference(
                    kind=TraceArtifactKind.HVM_EVIDENCE,
                    identifier=evidence_id,
                    parent_identifier=voice_release_id,
                )
                for evidence_id in interaction.component_evidence_ids
            )
        for pattern in guidance:
            traces.add(
                TraceReference(
                    kind=TraceArtifactKind.VKR_PATTERN,
                    identifier=pattern.pattern_id,
                    parent_identifier=virality_release_id,
                )
            )
            traces.update(
                TraceReference(
                    kind=TraceArtifactKind.VKR_EVIDENCE,
                    identifier=evidence_id,
                    parent_identifier=virality_release_id,
                )
                for evidence_id in pattern.supporting_evidence_ids
            )
        if retrieval_trace_id is not None:
            traces.add(
                TraceReference(kind=TraceArtifactKind.RETRIEVAL, identifier=retrieval_trace_id)
            )
        return tuple(
            sorted(
                traces,
                key=lambda item: (
                    item.kind.value,
                    item.identifier.int,
                    item.parent_identifier.int if item.parent_identifier else -1,
                ),
            )
        )
