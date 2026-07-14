"""Confidence composition orchestration without statistical estimation algorithms."""

from collections.abc import Mapping

from ceo_voice.analysis.contracts import ComposedConfidence, ConfidenceRequest
from ceo_voice.analysis.enums import ConfidenceMethod
from ceo_voice.analysis.ports import ConfidenceComposer
from ceo_voice.core.exceptions import ObservationBuildError


class ConfidenceComposerRegistry:
    """Instance-scoped method dispatch for current and future confidence strategies."""

    def __init__(self, composers: Mapping[ConfidenceMethod, ConfidenceComposer]) -> None:
        self._composers = dict(composers)

    def compose(self, request: ConfidenceRequest) -> ComposedConfidence:
        """Delegate to the registered strategy for the declared method."""

        try:
            composer = self._composers[request.method]
        except KeyError as exc:
            raise ObservationBuildError(
                "confidence method has no registered composer",
                details={"method": request.method.value},
            ) from exc
        return composer.compose(request)


class DeclaredConfidenceComposer:
    """Return an explicitly configured confidence contract without estimating confidence.

    This is suitable for exact deterministic measurements. Statistical, classifier, LLM, and
    evidence-weighted estimators can later implement the same port and be registered by method.
    """

    def __init__(self, result: ComposedConfidence) -> None:
        self._result = result

    def compose(self, request: ConfidenceRequest) -> ComposedConfidence:
        """Return the governed result supplied at composition time."""

        del request
        return self._result
