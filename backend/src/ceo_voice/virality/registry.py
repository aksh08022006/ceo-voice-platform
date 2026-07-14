"""Immutable structural feature and extractor registries."""

from collections.abc import Iterable
from typing import Protocol, cast, runtime_checkable
from uuid import UUID

from pydantic import Field, JsonValue

from ceo_voice.core.exceptions import ViralityError
from ceo_voice.models.base import ContractModel
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.virality.contracts import (
    ExtractionContext,
    ExtractorSpecification,
    FeatureReference,
    PatternMeasurement,
    RegistryReference,
    StructuralFeatureDefinition,
    Version,
)


@runtime_checkable
class StructuralExtractor(Protocol):
    """Source-independent interface implemented by every pattern extractor."""

    @property
    def specification(self) -> ExtractorSpecification:
        """Return immutable producer identity and feature ownership."""

        ...

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        """Classify content organization without producing personal style features."""

        ...


class StructuralFeatureRegistry(ContractModel):
    """Content-addressed vocabulary controlling all emitted structural patterns."""

    reference: RegistryReference
    definitions: tuple[StructuralFeatureDefinition, ...] = Field(min_length=1)

    @classmethod
    def build(
        cls,
        *,
        registry_id: UUID,
        version: Version,
        definitions: tuple[StructuralFeatureDefinition, ...],
    ) -> "StructuralFeatureRegistry":
        """Validate and content-address an ordered definition snapshot."""

        ordered = tuple(
            sorted(
                definitions,
                key=lambda item: (item.reference.feature_id, str(item.reference.version)),
            )
        )
        references = tuple(item.reference for item in ordered)
        if len(references) != len(set(references)):
            raise ViralityError("structural feature definitions must be unique")
        snapshot = sha256_text(dumps_json([item.model_dump(mode="json") for item in ordered]))
        return cls(
            reference=RegistryReference(
                registry_id=registry_id,
                version=version,
                snapshot_hash=snapshot,
            ),
            definitions=ordered,
        )

    def get(self, reference: FeatureReference) -> StructuralFeatureDefinition:
        """Resolve one exact feature definition."""

        for definition in self.definitions:
            if definition.reference == reference:
                return definition
        raise ViralityError(
            "unknown structural feature reference",
            details={"feature_id": reference.feature_id, "version": str(reference.version)},
        )


class ExtractorRegistry:
    """Validates feature ownership once and exposes deterministic execution order."""

    def __init__(
        self,
        extractors: Iterable[StructuralExtractor],
        feature_registry: StructuralFeatureRegistry,
    ) -> None:
        ordered = tuple(sorted(extractors, key=lambda item: item.specification.extractor_id))
        if not ordered:
            raise ViralityError("at least one structural extractor is required")
        ids = tuple(item.specification.extractor_id for item in ordered)
        if len(ids) != len(set(ids)):
            raise ViralityError("structural extractor IDs must be unique")
        owners: dict[FeatureReference, str] = {}
        for extractor in ordered:
            for feature in extractor.specification.features:
                definition = feature_registry.get(feature)
                if definition.extractor_id != extractor.specification.extractor_id:
                    raise ViralityError(
                        "extractor does not own its declared feature",
                        details={"feature_id": feature.feature_id},
                    )
                if feature in owners:
                    raise ViralityError(
                        "structural feature has multiple extractor owners",
                        details={"feature_id": feature.feature_id},
                    )
                owners[feature] = extractor.specification.extractor_id
        missing = {item.reference for item in feature_registry.definitions} - set(owners)
        if missing:
            raise ViralityError(
                "structural registry contains unowned features",
                details={"feature_ids": tuple(sorted(item.feature_id for item in missing))},
            )
        self._extractors = ordered

    @property
    def extractors(self) -> tuple[StructuralExtractor, ...]:
        """Return deterministic extractor order."""

        return self._extractors

    @property
    def signature(self) -> str:
        """Hash every producer identity for safe incremental build reuse."""

        payload = [item.specification.model_dump(mode="json") for item in self._extractors]
        return sha256_text(dumps_json(cast(JsonValue, payload)))
