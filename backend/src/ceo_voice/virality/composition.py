"""Default composition root for deterministic structural intelligence v1."""

from ceo_voice.virality.builder import ViralityLibraryBuilder
from ceo_voice.virality.contracts import AggregationPolicy
from ceo_voice.virality.extractors import default_extractors
from ceo_voice.virality.features import build_feature_registry
from ceo_voice.virality.ports import ViralityWorkspace
from ceo_voice.virality.registry import ExtractorRegistry


def create_virality_builder(
    *,
    workspace: ViralityWorkspace,
    policy: AggregationPolicy | None = None,
) -> ViralityLibraryBuilder:
    """Wire the governed catalog, deterministic extractors, and publication workspace."""

    registry = build_feature_registry()
    extractors = ExtractorRegistry(default_extractors(), registry)
    return ViralityLibraryBuilder(
        registry=registry,
        extractors=extractors,
        workspace=workspace,
        policy=policy,
    )
