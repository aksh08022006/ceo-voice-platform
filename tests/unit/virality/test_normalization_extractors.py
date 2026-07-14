"""Performance normalization and deterministic structural extraction tests."""

from uuid import UUID

import pytest

from ceo_voice.core.exceptions import ViralityError
from ceo_voice.models.enums import DocumentType
from ceo_voice.virality import (
    ExtractorRegistry,
    MetricCollectionMethod,
    PerformanceBasis,
    PerformanceMetrics,
    PerformanceNormalizer,
    StructuralDimension,
    ViralityCorpusItem,
    build_feature_registry,
)
from ceo_voice.virality.extractors import default_extractors
from ceo_voice.virality.pipeline import StructuralObservationPipeline
from tests.unit.analysis.factories import NOW
from tests.unit.virality.factories import corpus, document


def _structural_keys(content: str, *, thread_length: int = 1) -> set[str]:
    selected = corpus(1)
    item = selected.items[0].model_copy(
        update={"document": document(1, content=content, thread_length=thread_length)}
    )
    selected = selected.model_copy(update={"items": (item,)})
    registry = build_feature_registry()
    analysis = StructuralObservationPipeline(
        registry=registry,
        extractors=ExtractorRegistry(default_extractors(), registry),
        normalizer=PerformanceNormalizer(),
    ).analyze(selected, created_at=NOW)
    return {item.pattern_key for item in analysis.observations}


def test_performance_normalization_preserves_denominator_and_confounding() -> None:
    normalizer = PerformanceNormalizer()
    impression = normalizer.normalize(
        PerformanceMetrics(
            reactions=10,
            comments=2,
            shares=1,
            impressions=1_000,
            collected_at=NOW,
            method=MetricCollectionMethod.PLATFORM_API,
        )
    )
    audience = normalizer.normalize(
        PerformanceMetrics(
            reactions=10,
            audience_size=2_000,
            collected_at=NOW,
            method=MetricCollectionMethod.MANUAL,
        )
    )
    raw = normalizer.normalize(
        PerformanceMetrics(
            reactions=10,
            impressions=0,
            collected_at=NOW,
            method=MetricCollectionMethod.MANUAL,
        )
    )

    assert impression.basis is PerformanceBasis.IMPRESSIONS
    assert impression.score_per_thousand == 17
    assert impression.confounded is False
    assert audience.basis is PerformanceBasis.AUDIENCE and audience.confounded
    assert raw.basis is PerformanceBasis.RAW_ENGAGEMENT and len(raw.limitations) == 2


def test_pipeline_emits_registry_valid_content_free_evidence() -> None:
    registry = build_feature_registry()
    extractors = ExtractorRegistry(default_extractors(), registry)
    analysis = StructuralObservationPipeline(
        registry=registry,
        extractors=extractors,
        normalizer=PerformanceNormalizer(),
    ).analyze(corpus(1), created_at=NOW)

    assert len(analysis.observations) == 9
    assert {item.dimension for item in registry.definitions} == set(StructuralDimension)
    assert all(item.text_hash and not hasattr(item, "excerpt") for item in analysis.evidence)
    assert {item.pattern_key for item in analysis.observations} >= {
        "question",
        "short",
        "problem_solution",
        "audience_question",
        "single_post",
    }


def test_announcement_extractor_adds_only_applicable_structure() -> None:
    announcement = (
        "Today we are launching Atlas.\n\n"
        "It gives teams one place to plan.\n\n"
        "Read more at the link."
    )
    registry = build_feature_registry()
    analysis = StructuralObservationPipeline(
        registry=registry,
        extractors=ExtractorRegistry(default_extractors(), registry),
        normalizer=PerformanceNormalizer(),
    ).analyze(corpus(1, contents=(announcement,)), created_at=NOW)

    keys = {item.pattern_key for item in analysis.observations}
    assert {"announcement", "announcement_details", "details_first", "resource_direction"} <= keys
    assert len(analysis.observations) == 10


def test_extractor_rules_cover_the_governed_structural_vocabulary() -> None:
    cases = (
        ("7 lessons from scaling teams.\n\nData supports every lesson.\n\nStart today.", 2),
        ("However, the common playbook fails.\n\nBecause incentives matter.\n\nJoin us.", 8),
        (
            "I remember when we began.\n\nThe lesson we learned changed everything.\n\nKeep going.",
            1,
        ),
        ("A durable claim needs evidence.\n\nResearch shows the result.\n\nRead more here.", 1),
        ("Three operating rules:\n- Focus\n- Measure\n- Learn\n\nApply one now.", 1),
        ("Can a small team win?\n\nYes. Clear ownership compounds.\n\nShare your view.", 1),
        ("# OPERATING SYSTEM\n\nFirst define the goal. Then measure it. Finally review it.", 1),
        ("Today we are launching Atlas, now available to every team.\n\nDetails follow.", 1),
        ("Today we are launching Atlas after two years of research.\n\nDetails follow.", 1),
        (
            "A concise operating principle.\n\n" + " ".join(f"word{item}" for item in range(90)),
            1,
        ),
        (" ".join(f"word{item}" for item in range(90)), 1),
        (
            "Short.\n\nThis sentence contains many more words to create deliberately varied pacing across blocks.",
            1,
        ),
    )
    keys = set().union(*(_structural_keys(text, thread_length=thread) for text, thread in cases))

    assert {
        "numeric",
        "contrast",
        "personal_story",
        "direct_claim",
        "story_lesson",
        "claim_evidence",
        "listicle",
        "question_answer",
        "community_invitation",
        "direct_action",
        "none",
        "list_led",
        "heading_sectioned",
        "dense",
        "short_thread",
        "long_thread",
        "outcome_first",
        "context_first",
        "mixed",
        "varied",
    } <= keys


def test_corpus_item_rejects_non_social_and_prepublication_metrics() -> None:
    item = corpus(1).items[0]
    with pytest.raises(ValueError, match="social posts"):
        ViralityCorpusItem(
            document=item.document.model_copy(update={"document_type": DocumentType.BLOG_POST}),
            performance=item.performance,
        )
    with pytest.raises(ValueError, match="before publication"):
        ViralityCorpusItem(
            document=item.document,
            performance=item.performance.model_copy(update={"collected_at": NOW}),
        )
    with pytest.raises(ValueError, match="platform"):
        ViralityCorpusItem(
            document=document(1).model_copy(update={"platform": None}),
            performance=item.performance,
        )


class EmptyExtractor:
    @property
    def specification(self) -> object:
        return object()


def test_registries_reject_empty_and_unknown_feature_ownership() -> None:
    registry = build_feature_registry()
    with pytest.raises(ViralityError, match="at least one"):
        ExtractorRegistry((), registry)
    opening = next(
        item
        for item in default_extractors()
        if item.specification.extractor_id == "opening-extractor"
    )
    with pytest.raises(ViralityError, match="IDs must be unique"):
        ExtractorRegistry((opening, opening), registry)
    with pytest.raises(ViralityError, match="unowned"):
        ExtractorRegistry((opening,), registry)
    bad = registry.definitions[0].model_copy(
        update={
            "reference": registry.definitions[0].reference.model_copy(
                update={"feature_id": "unknown"}
            )
        }
    )
    with pytest.raises(ViralityError, match="unknown structural"):
        registry.get(bad.reference)
    assert UUID(int=1) != registry.reference.registry_id
