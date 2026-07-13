"""Tests for shared model invariants and boundary schemas."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.models import (
    ContextRole,
    Document,
    DocumentSourceType,
    EvaluationMetric,
    EvaluationResult,
    EvaluationStatus,
    FeatureScope,
    GenerationStatus,
    Metadata,
    Platform,
    RetrievedContext,
    RetrievedItem,
    VoiceFeature,
    VoiceFeatureLayer,
    VoiceProfile,
    VoiceProfileStatus,
)
from ceo_voice.schemas import (
    ErrorDetail,
    ErrorResponse,
    GenerationCandidate,
    GenerationRequest,
    GenerationResponse,
)


def test_document_preserves_voice_significant_whitespace(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    content = "  A short line.\n\nA deliberate break.  "
    metadata = Metadata(source_type=DocumentSourceType.BLOG, ingested_at=fixed_time)

    document = Document(
        id=UUID("30000000-0000-0000-0000-000000000003"),
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        content=content,
        checksum="a" * 64,
        metadata=metadata,
    )

    assert document.content == content
    assert document.metadata.language == "en"
    with pytest.raises(ValidationError):
        document.__setattr__("version", 2)


def test_document_rejects_blank_content(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    with pytest.raises(ValidationError, match="text must not be blank"):
        Document(
            id=UUID("30000000-0000-0000-0000-000000000003"),
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            content=" \n ",
            checksum="a" * 64,
            metadata=Metadata(source_type=DocumentSourceType.BLOG, ingested_at=fixed_time),
        )


def test_timestamps_are_normalized_to_utc() -> None:
    local_time = datetime(2026, 7, 13, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    metadata = Metadata(source_type=DocumentSourceType.OTHER, ingested_at=local_time)

    assert metadata.ingested_at == datetime(2026, 7, 13, 9, 30, tzinfo=UTC)


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone information"):
        Metadata(source_type=DocumentSourceType.OTHER, ingested_at=datetime(2026, 7, 13))


def test_voice_feature_scope_is_explicit() -> None:
    global_feature = VoiceFeature(
        name="sentence_length_variance",
        layer=VoiceFeatureLayer.SYNTACTIC,
        scope=FeatureScope.GLOBAL,
        value=0.72,
        confidence=0.8,
        evidence_count=12,
    )
    platform_feature = VoiceFeature(
        name="opening_line_break",
        layer=VoiceFeatureLayer.PLATFORM_BEHAVIOR,
        scope=FeatureScope.PLATFORM,
        platform=Platform.LINKEDIN,
        value=True,
        confidence=0.9,
        evidence_count=20,
    )

    assert global_feature.platform is None
    assert platform_feature.platform is Platform.LINKEDIN

    with pytest.raises(ValidationError, match="require a platform"):
        VoiceFeature(
            name="invalid",
            layer=VoiceFeatureLayer.FORMATTING,
            scope=FeatureScope.PLATFORM,
            value=True,
            confidence=0.5,
            evidence_count=1,
        )


def test_voice_profile_and_retrieved_context_are_provenance_aware(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    document_id = UUID("30000000-0000-0000-0000-000000000003")
    feature = VoiceFeature(
        name="contrast_transition",
        layer=VoiceFeatureLayer.RHETORICAL,
        scope=FeatureScope.GLOBAL,
        value="but",
        confidence=0.75,
        evidence_count=4,
        evidence_document_ids=(document_id,),
    )
    profile = VoiceProfile(
        id=UUID("40000000-0000-0000-0000-000000000004"),
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        version=1,
        status=VoiceProfileStatus.DRAFT,
        features=(feature,),
        source_snapshot_hash="b" * 64,
        created_at=fixed_time,
    )
    context = RetrievedContext(
        trace_id=UUID("50000000-0000-0000-0000-000000000005"),
        query="Explain the evidence",
        items=(
            RetrievedItem(
                document_id=document_id,
                content="  Evidence with original form.\n",
                role=ContextRole.VOICE_EVIDENCE,
                score=0.91,
                rank=1,
            ),
        ),
        generated_at=fixed_time,
    )

    assert profile.features[0].evidence_document_ids == (document_id,)
    assert context.items[0].role is ContextRole.VOICE_EVIDENCE
    assert context.items[0].content.startswith("  ")


def test_generation_and_evaluation_contracts_are_transport_neutral(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    profile_id = UUID("40000000-0000-0000-0000-000000000004")
    request = GenerationRequest(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        voice_profile_id=profile_id,
        voice_profile_version=3,
        platform=Platform.LINKEDIN,
        topic="Company learning",
        objective="Share a useful lesson",
        audience="Operators",
        candidate_count=2,
    )
    metric = EvaluationMetric(name="voice_fidelity", score=0.9, passed=True)
    candidate = GenerationCandidate(
        content="  Kept as authored.\n",
        evaluation=EvaluationResult(
            candidate_id=UUID("60000000-0000-0000-0000-000000000006"),
            status=EvaluationStatus.PASS,
            metrics=(metric,),
            evaluator_version="eval-1",
            created_at=fixed_time,
        ),
    )
    response = GenerationResponse(
        request_id=request.request_id,
        status=GenerationStatus.SUCCEEDED,
        candidates=(candidate,),
        created_at=fixed_time,
    )

    assert request.voice_profile_version == 3
    assert response.candidates[0].content.startswith("  ")


def test_error_response_rejects_unknown_fields() -> None:
    detail = ErrorDetail(code="invalid", message="Invalid request.", retryable=False)
    response = ErrorResponse(error=detail)

    assert response.request_id is None
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ErrorDetail.model_validate(
            {"code": "invalid", "message": "Invalid.", "retryable": False, "unknown": True}
        )
