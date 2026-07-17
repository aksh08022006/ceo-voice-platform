"""Explicit non-production review gate for exercising downstream generation."""

from typing import Any

from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.voice import DecisionState, FeatureRegistry


class ReviewedDevelopmentProfileBuilder:
    """Promote a human-reviewed development corpus without claiming production authority.

    The conservative Tier 1 builder intentionally publishes descriptive profiles that cannot
    generate. Local integration testing still needs to exercise retrieval and generation. This
    wrapper is the single explicit test gate for that promotion; production composition never
    installs it.
    """

    def __init__(self, builder: VoiceProfileBuilder, registry: FeatureRegistry) -> None:
        self._builder = builder
        self._registry = registry

    async def build(self, command: Any) -> Any:
        """Build normally, then authorize the reviewed artifact for development serving only."""

        profile = await self._builder.build(command)
        release = profile.managed_release.release

        def promoted(value: Any) -> Any:
            return value.model_copy(
                update={
                    "measurement_reliability": 1,
                    "attribution_reliability": 1,
                    "coverage": 1,
                    "effective_support": min(1, value.evidence_count),
                    "context_diversity": 1,
                    "stability": 1,
                    "cross_context_robustness": 1,
                    "nuisance_robustness": 1,
                    "distinctiveness": 1,
                    "freshness": 1,
                    "calibration": 1,
                    "independent_cluster_count": min(1, value.evidence_count),
                }
            )

        components = release.components.model_copy(
            update={
                field: tuple(
                    item.model_copy(
                        update={
                            "confidence": promoted(item.confidence),
                            "decision_state": DecisionState.ACTIONABLE_STRONG,
                        }
                    )
                    for item in getattr(release.components, field)
                )
                for field in ("aggregates", "residuals", "conditional_residuals")
            }
        )
        authorized = release.model_copy(
            update={"registry": self._registry.reference, "components": components}
        )
        report = profile.validation_report.model_copy(
            update={"release_content_hash": authorized.content_hash}
        )
        managed = profile.managed_release.model_copy(
            update={"release": authorized, "validation_report": report}
        )
        return profile.model_copy(
            update={
                "managed_release": managed,
                "validation_report": report,
                "corpus_health": profile.corpus_health.model_copy(
                    update={"generation_ready": True}
                ),
                "inspection": profile.inspection.model_copy(
                    update={"release_content_hash": authorized.content_hash}
                ),
                "retrieval_projection": profile.retrieval_projection.model_copy(
                    update={"release_content_hash": authorized.content_hash}
                ),
            }
        )
