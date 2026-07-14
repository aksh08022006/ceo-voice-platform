"""End-to-end corpus-to-published Virality Knowledge Release workflow."""

from typing import cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import JsonValue

from ceo_voice.core.exceptions import ViralityValidationError
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.virality.aggregation import PatternAggregator
from ceo_voice.virality.contracts import (
    AggregationPolicy,
    PublishedRelease,
    ViralityCorpus,
    ViralityProfile,
)
from ceo_voice.virality.enums import PublicationStatus
from ceo_voice.virality.inspection import build_inspection_report
from ceo_voice.virality.normalization import NORMALIZER_VERSION, PerformanceNormalizer
from ceo_voice.virality.pipeline import StructuralObservationPipeline
from ceo_voice.virality.ports import ViralityWorkspace
from ceo_voice.virality.registry import ExtractorRegistry, StructuralFeatureRegistry
from ceo_voice.virality.releases import build_analysis_snapshot, build_release
from ceo_voice.virality.validation import ViralityReleaseValidator


class ViralityLibraryBuilder:
    """Publish reusable structure intelligence without depending on personal voice."""

    def __init__(
        self,
        *,
        registry: StructuralFeatureRegistry,
        extractors: ExtractorRegistry,
        workspace: ViralityWorkspace,
        policy: AggregationPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._extractors = extractors
        self._workspace = workspace
        self._policy = policy or AggregationPolicy()
        self._pipeline = StructuralObservationPipeline(
            registry=registry,
            extractors=extractors,
            normalizer=PerformanceNormalizer(),
        )

    async def build(self, corpus: ViralityCorpus) -> ViralityProfile:
        """Analyze, validate, publish, and idempotently return one structural library."""

        fingerprint = self._fingerprint(corpus)
        existing = await self._workspace.get_by_fingerprint(
            corpus.tenant_id, corpus.library_id, fingerprint
        )
        if existing is not None:
            return existing
        history = await self._workspace.list_releases(corpus.tenant_id, corpus.library_id)
        previous = history[-1].publication.release if history else None
        version = previous.version + 1 if previous else 1
        release_id = uuid5(
            NAMESPACE_URL,
            f"{corpus.tenant_id}:{corpus.library_id}:{fingerprint}:{version}",
        )
        analysis = self._pipeline.analyze(corpus, created_at=corpus.created_at)
        analysis_snapshot = build_analysis_snapshot(
            snapshot_id=uuid5(NAMESPACE_URL, f"{release_id}:analysis"),
            analysis=analysis,
            corpus_id=corpus.id,
        )
        await self._workspace.save_analysis(analysis_snapshot, analysis)
        patterns = PatternAggregator(registry=self._registry, policy=self._policy).aggregate(
            analysis.observations,
            release_id=release_id,
        )
        release = build_release(
            release_id=release_id,
            tenant_id=corpus.tenant_id,
            library_id=corpus.library_id,
            version=version,
            previous_release_id=previous.id if previous else None,
            corpus_id=corpus.id,
            corpus_hash=sha256_text(dumps_json(self._corpus_payload(corpus))),
            registry=self._registry.reference,
            policy=self._policy,
            analysis_snapshot=analysis_snapshot,
            patterns=patterns,
            created_at=corpus.created_at,
        )
        validation = ViralityReleaseValidator(self._registry).validate(
            release,
            analysis,
            validated_at=corpus.created_at,
        )
        if not validation.is_valid():
            raise ViralityValidationError(
                "virality release failed structural validation",
                details={"issue_codes": tuple(item.code.value for item in validation.issues)},
            )
        profile = ViralityProfile(
            publication=PublishedRelease(
                release=release,
                validation=validation,
                status=PublicationStatus.ACTIVE,
                published_at=corpus.created_at,
            ),
            inspection=build_inspection_report(
                release,
                corpus,
                generated_at=corpus.created_at,
            ),
            build_fingerprint=fingerprint,
        )
        await self._workspace.publish(profile)
        return profile

    def _fingerprint(self, corpus: ViralityCorpus) -> str:
        payload = cast(
            JsonValue,
            {
                "builder_schema": "1.0.0",
                "corpus": self._corpus_payload(corpus),
                "registry": self._registry.reference.model_dump(mode="json"),
                "extractors": self._extractors.signature,
                "normalizer": NORMALIZER_VERSION.model_dump(mode="json"),
                "aggregation_policy": self._policy.model_dump(mode="json"),
            },
        )
        return sha256_text(dumps_json(payload))

    @staticmethod
    def _corpus_payload(corpus: ViralityCorpus) -> JsonValue:
        return cast(
            JsonValue,
            {
                "id": str(corpus.id),
                "tenant_id": str(corpus.tenant_id),
                "library_id": str(corpus.library_id),
                "dataset_version": corpus.dataset_version.model_dump(mode="json"),
                "label": corpus.label,
                "created_at": corpus.created_at.isoformat(),
                "items": [
                    item.model_dump(mode="json")
                    for item in sorted(
                        corpus.items,
                        key=lambda value: (value.document.id.int, value.document.version),
                    )
                ],
            },
        )
