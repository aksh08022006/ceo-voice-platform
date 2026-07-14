"""Immutable, content-addressed Feature Registry implementation."""

from functools import cmp_to_key
from typing import Self, cast
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.core.exceptions import FeatureRegistryError
from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.enums import VoiceDimension
from ceo_voice.voice.features import FeatureDefinition
from ceo_voice.voice.primitives import (
    FeatureId,
    FeatureReference,
    RegistryReference,
    SemanticVersion,
)


def _compare_definitions(left: FeatureDefinition, right: FeatureDefinition) -> int:
    """Order definitions canonically by ID and semantic-version precedence."""

    if left.feature_id != right.feature_id:
        return -1 if left.feature_id < right.feature_id else 1
    precedence = left.semantic_version.compare_precedence(right.semantic_version)
    if precedence != 0:
        return precedence
    left_version = str(left.semantic_version)
    right_version = str(right.semantic_version)
    if left_version == right_version:
        return 0
    return -1 if left_version < right_version else 1


class FeatureRegistry(ContractModel):
    """One immutable registry snapshot with deterministic resolution and evolution.

    The registry is injected into consumers; there is no process-global registry. Adding a feature
    creates a new snapshot and requires no modification to registry code.
    """

    id: UUID = Field(description="Stable registry lineage identifier.")
    version: SemanticVersion = Field(description="Immutable registry snapshot version.")
    definitions: tuple[FeatureDefinition, ...] = Field(
        min_length=1, description="Canonical ordered feature definitions."
    )
    created_at: UtcDatetime = Field(description="UTC snapshot creation time.")

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        """Reject duplicates, ambiguous precedence, and noncanonical ordering."""

        canonical = tuple(sorted(self.definitions, key=cmp_to_key(_compare_definitions)))
        if canonical != self.definitions:
            raise ValueError("feature definitions must use canonical registry ordering")
        references = tuple(definition.reference for definition in self.definitions)
        reference_keys = tuple(
            (reference.feature_id, str(reference.version)) for reference in references
        )
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("feature registry contains duplicate definition versions")
        for left, right in zip(self.definitions, self.definitions[1:], strict=False):
            if (
                left.feature_id == right.feature_id
                and left.semantic_version.compare_precedence(right.semantic_version) == 0
                and str(left.semantic_version) != str(right.semantic_version)
            ):
                raise ValueError("feature versions with equal precedence are ambiguous")
        return self

    @classmethod
    def build(
        cls,
        *,
        registry_id: UUID,
        version: SemanticVersion,
        definitions: tuple[FeatureDefinition, ...],
        created_at: UtcDatetime,
    ) -> Self:
        """Create a canonical snapshot from definitions supplied in any order."""

        ordered = tuple(sorted(definitions, key=cmp_to_key(_compare_definitions)))
        return cls(id=registry_id, version=version, definitions=ordered, created_at=created_at)

    @property
    def snapshot_hash(self) -> str:
        """Return a deterministic digest of semantically relevant snapshot content."""

        payload = cast(
            JsonValue,
            self.model_dump(mode="json", include={"id", "version", "definitions"}),
        )
        return sha256_text(dumps_json(payload))

    @property
    def reference(self) -> RegistryReference:
        """Return the content-addressed reference pinned by every HVM release."""

        return RegistryReference(
            registry_id=self.id,
            version=self.version,
            snapshot_hash=self.snapshot_hash,
        )

    def get(self, reference: FeatureReference) -> FeatureDefinition:
        """Resolve one exact definition or raise a stable domain exception."""

        for definition in self.definitions:
            if definition.reference == reference:
                return definition
        raise FeatureRegistryError(
            "feature definition was not found",
            details={
                "feature_id": reference.feature_id,
                "version": str(reference.version),
                "registry_version": str(self.version),
            },
        )

    def resolve_latest(self, feature_id: FeatureId) -> FeatureDefinition:
        """Resolve the highest-precedence definition for a stable feature ID."""

        matches = tuple(
            definition for definition in self.definitions if definition.feature_id == feature_id
        )
        if not matches:
            raise FeatureRegistryError(
                "feature definition was not found",
                details={"feature_id": feature_id, "registry_version": str(self.version)},
            )
        return matches[-1]

    def contains(self, reference: FeatureReference) -> bool:
        """Return whether the snapshot contains an exact definition reference."""

        return any(definition.reference == reference for definition in self.definitions)

    def for_dimension(self, dimension: VoiceDimension) -> tuple[FeatureDefinition, ...]:
        """Return definitions in one HVM dimension using canonical order."""

        return tuple(
            definition for definition in self.definitions if definition.dimension is dimension
        )

    def evolve(
        self,
        *,
        version: SemanticVersion,
        definitions: tuple[FeatureDefinition, ...],
        created_at: UtcDatetime,
    ) -> Self:
        """Return a new registry snapshot after a strictly increasing version change."""

        if version.compare_precedence(self.version) <= 0:
            raise FeatureRegistryError(
                "registry version must increase when evolving a snapshot",
                details={"current": str(self.version), "requested": str(version)},
            )
        return self.build(
            registry_id=self.id,
            version=version,
            definitions=definitions,
            created_at=created_at,
        )
