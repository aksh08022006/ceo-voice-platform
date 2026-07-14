"""Factual-anchor, human-edit, and bounded readability evaluation."""

import re
from difflib import SequenceMatcher
from statistics import fmean

from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.revoice import ReVoicedDraft

from .contracts import EvaluationInput, EvaluationMetric, EvaluationPolicy
from .enums import EvaluationDimension, MetricSource
from .metrics import metric
from .stylometry import factual_anchors, paragraphs, sentences, words


class PreservationEvaluator:
    """Measure observable preservation without claiming semantic or factual certainty."""

    def evaluate(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        return (
            *self._factual(value, policy),
            *self._edit(value, policy),
            *self._readability(value, policy),
        )

    def _factual(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        factual_evidence = tuple(
            item
            for item in value.retrieval.evidence
            if EvidencePurpose.FACTUAL_SUPPORT in item.purposes
        )
        allowed_text = "\n".join(
            (
                value.context.intent.topic,
                value.context.intent.objective,
                value.context.intent.audience,
                *(item.content for item in factual_evidence),
            )
        )
        if value.edited_draft is not None:
            allowed_text += "\n" + value.edited_draft.content
        allowed = {item.casefold() for item in factual_anchors(allowed_text)}
        observed = factual_anchors(value.draft.content)
        unsupported = tuple(item for item in observed if item.casefold() not in allowed)
        support_score = 1 - len(unsupported) / max(1, len(observed))
        metrics = [
            metric(
                "factual.observable_anchor_support",
                EvaluationDimension.FACTUAL_PRESERVATION,
                support_score,
                "Numbers, names, quotations, URLs, mentions, and hashtags were checked against supplied evidence and intent.",
                policy,
                evidence=tuple(item.evidence_id for item in factual_evidence),
                diagnostics={
                    "observed_anchors": list(observed),
                    "unsupported_anchors": list(unsupported),
                    "limitation": "anchor support is not semantic fact verification",
                },
            )
        ]
        if isinstance(value.draft, ReVoicedDraft):
            validation = value.draft.report.final_validation
            preserved = validation.protected_regions_preserved / max(
                1, validation.protected_regions_total
            )
            metrics.append(
                metric(
                    "factual.revoice_protected_regions",
                    EvaluationDimension.FACTUAL_PRESERVATION,
                    preserved,
                    "Re-Voice protected-region preservation was verified by its independent report.",
                    policy,
                )
            )
        return tuple(metrics)

    def _edit(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        if value.edited_draft is None or not isinstance(value.draft, ReVoicedDraft):
            return (
                metric(
                    "edit.not_applicable",
                    EvaluationDimension.EDIT_PRESERVATION,
                    1,
                    "Edit preservation applies only to Re-Voice outputs.",
                    policy,
                    applicable=False,
                ),
            )
        edited = value.edited_draft.content
        output = value.draft.content
        similarity = SequenceMatcher(None, edited, output, autojunk=False).ratio()
        validation = value.draft.report.final_validation
        protected = validation.protected_regions_preserved / max(
            1, validation.protected_regions_total
        )
        changed_editable = len(value.draft.report.changed_regions) / max(
            1, len(value.draft.report.regions.editable)
        )
        return (
            metric(
                "edit.lexical_preservation",
                EvaluationDimension.EDIT_PRESERVATION,
                similarity,
                "Lexical similarity bounds edit drift but is not a semantic-equivalence proof.",
                policy,
                source=MetricSource.STYLOMETRIC,
            ),
            metric(
                "edit.protected_region_preservation",
                EvaluationDimension.EDIT_PRESERVATION,
                protected,
                "All deterministically protected human and factual regions were checked.",
                policy,
            ),
            metric(
                "edit.editable_region_activity",
                EvaluationDimension.EDIT_PRESERVATION,
                changed_editable,
                "The fraction of permitted editable regions actually modified was measured.",
                policy,
                applicable=bool(value.draft.report.regions.editable),
            ),
            metric(
                "edit.revoice_constraint_validation",
                EvaluationDimension.EDIT_PRESERVATION,
                float(validation.valid),
                "Re-Voice final constraint validation was retained as an independent signal.",
                policy,
            ),
        )

    def _readability(
        self, value: EvaluationInput, policy: EvaluationPolicy
    ) -> tuple[EvaluationMetric, ...]:
        content = value.draft.content
        sentence_lengths = tuple(len(words(item)) for item in sentences(content))
        paragraph_lengths = tuple(len(words(item)) for item in paragraphs(content))
        mean_sentence = fmean(sentence_lengths) if sentence_lengths else 0
        longest_sentence = max(sentence_lengths, default=0)
        empty_line_runs = len(re.findall(r"\n{4,}", content))
        sentence_score = (
            1.0 if 4 <= mean_sentence <= 30 else max(0, 1 - abs(mean_sentence - 17) / 17)
        )
        return (
            metric(
                "readability.sentence_length",
                EvaluationDimension.READABILITY,
                sentence_score,
                "Mean sentence length was checked against a broad legibility band.",
                policy,
                source=MetricSource.STYLOMETRIC,
                diagnostics={"mean_words": mean_sentence},
            ),
            metric(
                "readability.long_sentence",
                EvaluationDimension.READABILITY,
                float(longest_sentence <= 60),
                "Extremely long sentences were detected deterministically.",
                policy,
                diagnostics={"longest_words": longest_sentence},
            ),
            metric(
                "readability.paragraph_presence",
                EvaluationDimension.READABILITY,
                float(bool(paragraph_lengths)),
                "At least one non-empty paragraph is required.",
                policy,
            ),
            metric(
                "readability.whitespace_sanity",
                EvaluationDimension.READABILITY,
                float(empty_line_runs == 0),
                "Excessive consecutive blank-line runs were checked without normalizing formatting.",
                policy,
                diagnostics={"excessive_runs": empty_line_runs},
            ),
        )
