"""Corpus health, profile inspection, and retrieval-projection materialization."""

from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ceo_voice.analysis import AnalysisRunStatus, AnalyzerRunStatus
from ceo_voice.models.base import UtcDatetime
from ceo_voice.profiles.contracts import (
    CorpusHealthIssue,
    CorpusHealthReport,
    CorpusObservationBatch,
    CuratedCorpus,
    FeatureInspection,
    ProfileBuildPolicy,
    ProfileInspectionReport,
)
from ceo_voice.profiles.enums import CorpusHealthStatus, ProfileAuthority
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice import (
    FeatureRegistry,
    HVMRelease,
    ManagedRelease,
    RetrievalProjection,
    RetrievalProjectionType,
    ScalarValue,
    SemanticVersion,
)


def build_corpus_health(
    *,
    corpus_hash: str,
    corpus: CuratedCorpus,
    batch: CorpusObservationBatch,
    policy: ProfileBuildPolicy,
) -> CorpusHealthReport:
    """Calculate transparent corpus coverage and operational eligibility."""

    successful = sum(item.status is AnalysisRunStatus.SUCCEEDED for item in batch.observation_sets)
    partial = sum(item.status is AnalysisRunStatus.PARTIAL for item in batch.observation_sets)
    failed = len(batch.failures)
    total = len(corpus.documents)
    observations = tuple(
        observation
        for observation_set in batch.observation_sets
        for observation in observation_set.observations
    )
    evidence_ids = {
        unit.id
        for observation_set in batch.observation_sets
        for unit in observation_set.evidence_units
    }
    failed_analyzers = sum(
        record.status is AnalyzerRunStatus.FAILED
        for observation_set in batch.observation_sets
        for record in observation_set.execution_trace
    )
    publication_dates = tuple(
        item.document.publication_date
        for item in corpus.documents
        if item.document.publication_date is not None
    )
    issues: list[CorpusHealthIssue] = []
    if successful + partial < policy.minimum_successful_documents:
        issues.append(
            CorpusHealthIssue(
                code="insufficient_successful_documents",
                message=(
                    f"Corpus has {successful + partial} analyzable documents; "
                    f"at least {policy.minimum_successful_documents} are required."
                ),
                blocking=True,
            )
        )
    failed_fraction = failed / total
    if failed_fraction > policy.maximum_failed_fraction:
        issues.append(
            CorpusHealthIssue(
                code="excessive_document_failures",
                message=f"Document failure fraction {failed_fraction:.2%} exceeds policy.",
                blocking=True,
            )
        )
    if partial:
        issues.append(
            CorpusHealthIssue(
                code="partial_analysis",
                message=f"{partial} documents contain partial analyzer output.",
                blocking=False,
            )
        )
    if not publication_dates:
        issues.append(
            CorpusHealthIssue(
                code="missing_temporal_coverage",
                message="No document has a publication timestamp.",
                blocking=False,
            )
        )
    issues.append(
        CorpusHealthIssue(
            code="descriptive_tier1_only",
            message=(
                "Tier 1 measurements are descriptive; no calibrated cohort distinctiveness, "
                "nuisance robustness, or generation authority is claimed."
            ),
            blocking=False,
        )
    )
    platforms = tuple(
        sorted(
            {item.document.platform for item in corpus.documents if item.document.platform},
            key=str,
        )
    )
    languages = tuple(sorted({item.document.language for item in corpus.documents}))
    sources = tuple(sorted({item.document.source for item in corpus.documents}, key=str))
    build_eligible = not any(item.blocking for item in issues) and bool(observations)
    # Corpus volume alone cannot grant generation authority. Tier 1 intentionally has no
    # calibrated distinctiveness or nuisance-robustness evidence, so this remains false even
    # when the corpus exceeds the production volume thresholds.
    generation_ready = False
    return CorpusHealthReport(
        corpus_hash=corpus_hash,
        status=(
            CorpusHealthStatus.BLOCKED
            if not build_eligible
            else CorpusHealthStatus.HEALTHY if not issues else CorpusHealthStatus.WARNING
        ),
        total_documents=total,
        successful_documents=successful,
        partial_documents=partial,
        failed_documents=failed,
        reused_documents=batch.reused_documents,
        observation_count=len(observations),
        observed_feature_count=len(
            {item.feature for item in observations if item.value is not None}
        ),
        evidence_unit_count=len(evidence_ids),
        total_characters=sum(len(item.document.content) for item in corpus.documents),
        total_words=sum(len(item.document.content.split()) for item in corpus.documents),
        platforms=platforms,
        languages=languages,
        sources=sources,
        earliest_publication=min(publication_dates) if publication_dates else None,
        latest_publication=max(publication_dates) if publication_dates else None,
        missing_publication_dates=total - len(publication_dates),
        failed_analyzers=failed_analyzers,
        build_eligible=build_eligible,
        generation_ready=generation_ready,
        issues=tuple(issues),
    )


def build_inspection_report(
    *,
    managed_release: ManagedRelease,
    registry: FeatureRegistry,
    health: CorpusHealthReport,
    generated_at: UtcDatetime,
) -> ProfileInspectionReport:
    """Create a deterministic report from published scalar components."""

    release = managed_release.release
    features: list[FeatureInspection] = []
    for aggregate in release.components.aggregates:
        if not isinstance(aggregate.value, ScalarValue):
            continue
        definition = registry.get(aggregate.feature)
        features.append(
            FeatureInspection(
                feature=aggregate.feature,
                display_name=definition.display_name,
                dimension=definition.dimension.value,
                value=aggregate.value,
                decision_state=aggregate.decision_state.value,
                confidence_coverage=aggregate.confidence.coverage,
                evidence_count=aggregate.confidence.evidence_count,
                platform=aggregate.context.platform,
            )
        )
    for conditional in release.components.conditional_residuals:
        if not isinstance(conditional.delta, ScalarValue):
            continue
        definition = registry.get(conditional.feature)
        features.append(
            FeatureInspection(
                feature=conditional.feature,
                display_name=f"{definition.display_name} delta",
                dimension=definition.dimension.value,
                value=conditional.delta,
                decision_state=conditional.decision_state.value,
                confidence_coverage=conditional.confidence.coverage,
                evidence_count=conditional.confidence.evidence_count,
                platform=conditional.condition.platform,
            )
        )
    authority = (
        ProfileAuthority.GENERATION_READY
        if health.generation_ready
        else ProfileAuthority.DESCRIPTIVE
    )
    summary = (
        f"Profile v{release.version} for voice identity {release.voice_identity_id} is "
        f"{managed_release.status.value}. It summarizes {len(release.components.aggregates)} "
        f"Tier 1 behaviors from {health.successful_documents + health.partial_documents} "
        f"documents across {len(health.platforms)} platform(s). Its authority is "
        f"{authority.value}; values are evidence-backed descriptive measurements, not an "
        "empirically calibrated claim of author distinctiveness."
    )
    return ProfileInspectionReport(
        release_id=release.id,
        release_version=release.version,
        release_status=managed_release.status,
        release_content_hash=release.content_hash,
        authority=authority,
        summary=summary,
        features=tuple(
            sorted(
                features,
                key=lambda item: (
                    item.feature.feature_id,
                    str(item.platform) if item.platform else "",
                ),
            )
        ),
        limitations=tuple(item.message for item in health.issues),
        generated_at=generated_at,
    )


def build_retrieval_projection(
    *,
    projection_id: UUID,
    release: HVMRelease,
    materialized_at: UtcDatetime,
) -> RetrievalProjection:
    """Materialize the release's feature/component index without retrieval logic."""

    feature_set = {item.feature for item in release.components.residuals} | {
        item.feature for item in release.components.conditional_residuals
    }
    features = tuple(
        sorted(
            feature_set,
            key=lambda item: (item.feature_id, str(item.version)),
        )
    )
    component_ids = tuple(
        sorted(
            (
                *(item.id for item in release.components.residuals),
                *(item.id for item in release.components.conditional_residuals),
            ),
            key=lambda item: item.int,
        )
    )
    payload = cast(
        JsonValue,
        {
            "release_id": str(release.id),
            "release_content_hash": release.content_hash,
            "features": [item.model_dump(mode="json") for item in features],
            "component_ids": [str(item) for item in component_ids],
        },
    )
    return RetrievalProjection(
        id=projection_id,
        tenant_id=release.tenant_id,
        voice_identity_id=release.voice_identity_id,
        release_id=release.id,
        release_content_hash=release.content_hash,
        projection_type=RetrievalProjectionType.FEATURE_INDEX,
        indexed_features=features,
        indexed_component_ids=component_ids,
        projection_version=SemanticVersion.parse("1.0.0"),
        projection_hash=sha256_text(dumps_json(payload)),
        materialized_at=materialized_at,
    )
