"""Default local composition root for the executable Tier 1 profile workflow."""

from ceo_voice.analysis import (
    AnalysisEngine,
    AnalyzerRegistry,
    ComposedConfidence,
    DeclaredConfidenceComposer,
    DeterministicDocumentAnalyzer,
)
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.profiles.contracts import ProfileBuildPolicy
from ceo_voice.profiles.ports import ProfileWorkspace, ProgressSink
from ceo_voice.profiles.tier1 import Tier1Runtime, build_tier1_runtime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.voice import EvidenceWeightComponents, SemanticVersion


def create_tier1_profile_builder(
    *,
    workspace: ProfileWorkspace,
    policy: ProfileBuildPolicy | None = None,
    progress: ProgressSink | None = None,
    runtime: Tier1Runtime | None = None,
) -> VoiceProfileBuilder:
    """Wire the stable kernels to conservative Tier 1 production implementations."""

    selected = runtime or build_tier1_runtime()
    analyzer_registry = AnalyzerRegistry(selected.analyzers)
    analyzer_signature = sha256_text(
        "|".join(
            ":".join(
                (
                    item.specification.analyzer_id,
                    str(item.specification.version),
                    item.specification.configuration_hash,
                )
            )
            for item in analyzer_registry.analyzers
        )
    )
    analysis_engine = AnalysisEngine(
        analyzer_registry=analyzer_registry,
        feature_registry=selected.registry,
        document_analyzer=DeterministicDocumentAnalyzer(
            segmentation_version=SemanticVersion.parse("1.0.0")
        ),
        confidence_composer=DeclaredConfidenceComposer(
            ComposedConfidence(
                quality=1,
                evidence_weights=EvidenceWeightComponents(
                    target_attribution=1,
                    speaker_attribution=1,
                    source_reliability=1,
                    modality_admissibility=1,
                    observation_quality=1,
                    independence=1,
                    context_relevance=1,
                    temporal_relevance=1,
                    rights_admissible=True,
                ),
            )
        ),
    )
    return VoiceProfileBuilder(
        analysis_engine=analysis_engine,
        registry=selected.registry,
        baselines=selected.baselines,
        workspace=workspace,
        analyzer_signature=analyzer_signature,
        policy=policy,
        progress=progress,
    )
