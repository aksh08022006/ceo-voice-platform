"""Isolated behavior tests for structural analysis and Tier 1 analyzers."""

import asyncio

import pytest

from ceo_voice.analysis import (
    AnalysisRequest,
    AnalyzerContext,
    DeterministicDocumentAnalyzer,
    MeasurementCandidate,
)
from ceo_voice.voice import ObservationState, ScalarValue, SourceModality
from tests.unit.analysis.factories import (
    NOW,
    RUN_ID,
    analyzers,
    clean_document,
    identity,
    semver,
)


def request_for_document(
    *, content: str = "# BUILD\n\nHello CEO world!", metadata: dict[str, object] | None = None
) -> AnalysisRequest:
    """Return a deterministic request using optional clean-document overrides."""

    return AnalysisRequest(
        run_id=RUN_ID,
        document=clean_document(content=content, metadata=metadata),
        voice_identity=identity(),
        source_modality=SourceModality.AUTHORED_WRITTEN,
        event_time=NOW,
        created_at=NOW,
    )


def context_for(
    *, content: str = "# BUILD\n\nHello CEO world!", metadata: dict[str, object] | None = None
) -> AnalyzerContext:
    """Build a fully segmented analyzer context."""

    request = request_for_document(content=content, metadata=metadata)
    analyzed = DeterministicDocumentAnalyzer(segmentation_version=semver()).analyze(
        request.document
    )
    return AnalyzerContext(request=request, analyzed_document=analyzed)


def value_map(candidates: tuple[MeasurementCandidate, ...]) -> dict[str, float | None]:
    """Project scalar candidate values by feature ID."""

    output: dict[str, float | None] = {}
    for item in candidates:
        feature = item.feature
        value = item.value
        output[feature.feature_id] = value.value if isinstance(value, ScalarValue) else None
    return output


def test_document_analysis_produces_stable_nested_addresses() -> None:
    context = context_for(content="First sentence. Second?\n\nThird!\nline two")
    analyzed = context.analyzed_document

    assert len(analyzed.paragraphs) == 2
    assert len(analyzed.sentences) == 4
    assert len(analyzed.lines) == 3
    assert analyzed.text_for(analyzed.sentences[1]) == "Second?"
    assert analyzed.sentences[0].paragraph_id == analyzed.paragraphs[0].id
    assert analyzed.span(analyzed.document_span.id) == analyzed.document_span
    assert analyzed == DeterministicDocumentAnalyzer(segmentation_version=semver()).analyze(
        context.request.document
    )
    with pytest.raises(KeyError):
        analyzed.span(RUN_ID)


def test_document_statistics_analyzer_includes_missing_and_declared_thread_length() -> None:
    analyzer = analyzers()[0]
    missing = asyncio.run(analyzer.analyze(context_for(content="One two three.")))
    present = asyncio.run(
        analyzer.analyze(context_for(content="One two three.", metadata={"thread_length": 4}))
    )

    assert len(missing) == 5
    assert missing[-1].state is ObservationState.MISSING
    assert value_map(present) == {
        "analysis.character-count": 14.0,
        "analysis.word-count": 3.0,
        "analysis.reading-time": 0.9,
        "analysis.document-length": 14.0,
        "analysis.thread-length": 4.0,
    }
    assert all(candidate.evidence_span_ids for candidate in present)


@pytest.mark.parametrize("thread_value", [True, 0, -1, "3"])
def test_document_statistics_rejects_non_positive_or_non_integer_thread_metadata(
    thread_value: object,
) -> None:
    candidate = asyncio.run(
        analyzers()[0].analyze(
            context_for(content="A document.", metadata={"thread_length": thread_value})
        )
    )[-1]
    assert candidate.state is ObservationState.MISSING


def test_structural_analyzer_measures_document_layout() -> None:
    candidates = asyncio.run(
        analyzers()[1].analyze(
            context_for(content="# Heading\n\nOne short. Two words?\n- first\n2. second")
        )
    )
    values = value_map(candidates)

    assert values["analysis.sentence-count"] == 4
    assert values["analysis.paragraph-count"] == 2
    assert values["analysis.line-break-count"] == 4
    assert values["analysis.list-item-count"] == 2
    assert values["analysis.heading-count"] == 1
    assert values["analysis.mean-sentence-words"] == 2
    assert values["analysis.mean-paragraph-words"] == 4


def test_symbol_analyzer_measures_visible_markers() -> None:
    candidates = asyncio.run(
        analyzers()[2].analyze(
            context_for(content="Really?! @ceo #Build https://example.com/path.\nYes — ship it! 🚀")
        )
    )
    values = value_map(candidates)

    assert values["analysis.emoji-count"] == 1
    assert values["analysis.question-frequency"] == pytest.approx(1 / 3)
    assert values["analysis.exclamation-frequency"] == pytest.approx(2 / 3)
    assert values["analysis.link-count"] == 1
    assert values["analysis.hashtag-count"] == 1
    assert values["analysis.mention-count"] == 1
    assert values["analysis.punctuation-count"] is not None
    assert values["analysis.punctuation-count"] >= 8


def test_formatting_analyzer_handles_casing_and_whitespace() -> None:
    candidates = asyncio.run(
        analyzers()[3].analyze(context_for(content="CEO ships  FAST.\n\nnext line"))
    )
    values = value_map(candidates)

    assert values["analysis.capitalization-ratio"] == pytest.approx(7 / 20)
    assert values["analysis.uppercase-word-ratio"] == pytest.approx(2 / 5)
    assert values["analysis.blank-line-count"] == 1
    assert values["analysis.repeated-whitespace-count"] == 1


def test_analyzers_handle_zero_denominators_without_non_finite_values() -> None:
    context = context_for(content="🚀")
    structural = value_map(asyncio.run(analyzers()[1].analyze(context)))
    formatting = value_map(asyncio.run(analyzers()[3].analyze(context)))

    assert structural["analysis.mean-sentence-words"] == 0
    assert formatting["analysis.capitalization-ratio"] == 0
    assert formatting["analysis.uppercase-word-ratio"] == 0


def test_analyzer_specifications_expose_all_required_capabilities() -> None:
    for analyzer in analyzers():
        specification = analyzer.specification
        assert specification.supported_features
        assert specification.required_inputs
        assert specification.all_platforms
        assert specification.all_languages
        assert specification.measurement_class.value == "deterministic"
        assert specification.dependencies == ()
