"""Aggregate-only projections for reviewer-facing HVM inspection."""

from collections import Counter, defaultdict
from enum import Enum

from pydantic import JsonValue

from ceo_voice.profiles import FeatureInspection
from ceo_voice.services.published_profiles import PublishedProfileBundle

from .schemas import (
    ComparisonValueResponse,
    CorpusAnalyticsResponse,
    CorpusIssueResponse,
    CountBreakdownResponse,
    DimensionCoverageResponse,
    FeatureComparisonResponse,
    FeatureMetricResponse,
    ProfileAnalyticsResponse,
    ReleaseAnalyticsResponse,
)

EVIDENCE_COUNT_EXPLANATION = (
    "Evidence units are immutable document, paragraph, or sentence spans. A feature support count "
    "records feature-to-evidence links and can therefore exceed both the number of posts and the "
    "number of unique evidence units. It must not be interpreted as additional documents."
)
HVM_FORMULA = "platform target = leader core behavior + platform-specific residual"
TRUST_STATEMENT = (
    "This release is an evidence-backed descriptive model of the available corpus. Structural "
    "validation proves internal integrity and traceability; it does not prove authorship identity, "
    "human-perceived indistinguishability, or endorsement by the named person."
)


def project_profile_analytics(
    bundle: PublishedProfileBundle,
    peers: tuple[PublishedProfileBundle, ...],
) -> ProfileAnalyticsResponse:
    """Project one published bundle without returning source text or private tenant identifiers."""

    profile = bundle.voice_profile
    health = profile.corpus_health
    inspection = profile.inspection
    release = profile.managed_release.release
    documents = tuple(item.document for item in bundle.voice_corpus.documents)
    platform_counts = Counter(
        _label(document.platform) for document in documents if document.platform is not None
    )
    source_counts = Counter(_label(document.source) for document in documents)
    language_counts = Counter(document.language for document in documents)
    document_type_counts = Counter(_label(document.document_type) for document in documents)
    content_type_counts = Counter(
        _metadata_text(document.metadata.get("content_type"), "unspecified")
        for document in documents
    )
    source_modality_counts = Counter(
        _label(item.source_modality) for item in bundle.voice_corpus.documents
    )
    acquisition_counts = Counter(
        _metadata_text(document.metadata.get("acquisition_method"), "unspecified")
        for document in documents
    )
    capture_counts = Counter(
        _metadata_text(document.metadata.get("capture_medium"), "unspecified")
        for document in documents
    )
    evidence_type_counts = Counter(_label(unit.unit_type) for unit in profile.evidence_units)
    features = tuple(_project_feature(item) for item in inspection.features)

    return ProfileAnalyticsResponse(
        slug=bundle.slug,
        name=bundle.name,
        role=bundle.role,
        summary=bundle.summary,
        corpus=CorpusAnalyticsResponse(
            corpus_hash=health.corpus_hash,
            health_status=_label(health.status),
            total_documents=health.total_documents,
            successful_documents=health.successful_documents,
            partial_documents=health.partial_documents,
            failed_documents=health.failed_documents,
            reused_documents=health.reused_documents,
            observation_count=health.observation_count,
            observed_feature_count=health.observed_feature_count,
            evidence_unit_count=health.evidence_unit_count,
            total_characters=health.total_characters,
            total_words=health.total_words,
            exact_publication_dates=health.total_documents - health.missing_publication_dates,
            missing_publication_dates=health.missing_publication_dates,
            earliest_publication=health.earliest_publication,
            latest_publication=health.latest_publication,
            build_eligible=health.build_eligible,
            generation_enabled_for_evaluation=health.generation_ready,
            failed_analyzers=health.failed_analyzers,
            platforms=_breakdown(platform_counts),
            sources=_breakdown(source_counts),
            languages=_breakdown(language_counts),
            document_types=_breakdown(document_type_counts),
            content_types=_breakdown(content_type_counts),
            source_modalities=_breakdown(source_modality_counts),
            acquisition_methods=_breakdown(acquisition_counts),
            capture_media=_breakdown(capture_counts),
            evidence_unit_types=_breakdown(evidence_type_counts),
            reposts=sum(document.metadata.get("is_repost") is True for document in documents),
            quote_posts=sum(
                document.metadata.get("is_quote_post") is True for document in documents
            ),
            uncertain_documents=sum(
                _metadata_number(document.metadata.get("uncertain_span_count")) > 0
                for document in documents
            ),
            development_only_documents=sum(
                document.metadata.get("development_only") is True for document in documents
            ),
            issues=tuple(
                CorpusIssueResponse(
                    code=issue.code,
                    message=issue.message,
                    blocking=issue.blocking,
                )
                for issue in health.issues
            ),
        ),
        release=ReleaseAnalyticsResponse(
            release_id=release.id,
            version=release.version,
            status=_label(profile.managed_release.status),
            artifact_status=bundle.artifact_status,
            authority=_label(inspection.authority),
            content_hash=release.content_hash,
            previous_release_id=release.previous_release_id,
            registry_version=str(release.registry.version),
            registry_hash=release.registry.snapshot_hash,
            compiler_version=str(release.compiler_version),
            validator_version=str(profile.validation_report.validator_version),
            structurally_valid=profile.validation_report.is_valid(),
            validation_issue_count=len(profile.validation_report.issues),
            lifecycle_event_count=len(profile.managed_release.events),
            created_at=release.created_at,
            published_at=profile.published_at,
            inspected_at=inspection.generated_at,
            summary=inspection.summary,
        ),
        dimensions=_dimension_coverage(features),
        features=features,
        comparisons=_comparisons(bundle, peers),
        limitations=inspection.limitations,
        evidence_count_explanation=EVIDENCE_COUNT_EXPLANATION,
        hvm_formula=HVM_FORMULA,
        trust_statement=TRUST_STATEMENT,
    )


def _project_feature(feature: FeatureInspection) -> FeatureMetricResponse:
    return FeatureMetricResponse(
        feature_id=feature.feature.feature_id,
        version=str(feature.feature.version),
        display_name=feature.display_name,
        dimension=feature.dimension,
        value=feature.value.value,
        unit=feature.value.unit,
        decision_state=feature.decision_state,
        confidence_coverage=feature.confidence_coverage,
        support_count=feature.evidence_count,
        platform=_label(feature.platform) if feature.platform is not None else None,
        scope="core" if feature.platform is None else "platform_residual",
    )


def _dimension_coverage(
    features: tuple[FeatureMetricResponse, ...],
) -> tuple[DimensionCoverageResponse, ...]:
    grouped: dict[str, list[FeatureMetricResponse]] = defaultdict(list)
    for feature in features:
        grouped[feature.dimension].append(feature)
    response: list[DimensionCoverageResponse] = []
    for dimension, components in grouped.items():
        core = tuple(item for item in components if item.scope == "core")
        coverage = sum(item.confidence_coverage for item in core) / len(core) if core else 0.0
        response.append(
            DimensionCoverageResponse(
                dimension=dimension,
                core_feature_count=len(core),
                total_component_count=len(components),
                average_coverage=coverage,
                support_links=sum(item.support_count for item in components),
            )
        )
    return tuple(sorted(response, key=lambda item: item.dimension))


def _comparisons(
    target: PublishedProfileBundle,
    peers: tuple[PublishedProfileBundle, ...],
) -> tuple[FeatureComparisonResponse, ...]:
    peer_values: dict[str, list[ComparisonValueResponse]] = defaultdict(list)
    target_definitions = {
        feature.feature.feature_id: (
            feature.display_name,
            feature.dimension,
            feature.value.unit,
            str(feature.feature.version),
        )
        for feature in target.voice_profile.inspection.features
        if feature.platform is None
    }
    for peer in peers:
        for feature in peer.voice_profile.inspection.features:
            if feature.platform is not None:
                continue
            feature_id = feature.feature.feature_id
            definition = target_definitions.get(feature_id)
            if definition is None or (
                feature.value.unit,
                str(feature.feature.version),
            ) != (definition[2], definition[3]):
                continue
            peer_values[feature_id].append(
                ComparisonValueResponse(
                    profile_slug=peer.slug,
                    profile_name=peer.name,
                    value=feature.value.value,
                )
            )
    return tuple(
        FeatureComparisonResponse(
            feature_id=feature_id,
            display_name=target_definitions[feature_id][0],
            dimension=target_definitions[feature_id][1],
            unit=target_definitions[feature_id][2],
            values=tuple(sorted(values, key=lambda item: item.profile_name)),
        )
        for feature_id, values in sorted(peer_values.items())
        if len(values) > 1
    )


def _breakdown(counts: Counter[str]) -> tuple[CountBreakdownResponse, ...]:
    return tuple(
        CountBreakdownResponse(label=label, count=count) for label, count in sorted(counts.items())
    )


def _label(value: object) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def _metadata_text(value: JsonValue | None, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _metadata_number(value: JsonValue | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)
