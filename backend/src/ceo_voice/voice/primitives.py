"""Small immutable value objects shared across HVM domain modules."""

import re
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from ceo_voice.models.base import (
    ContractModel,
    NonEmptyStr,
    UtcDatetime,
    normalize_utc_datetime,
)
from ceo_voice.models.enums import DocumentType, Platform
from ceo_voice.voice.enums import ProducerType

FeatureId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=200,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$",
    ),
]
LanguageTag = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
    ),
]
Sha256Digest = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$"),
]
UnitInterval = Annotated[float, Field(ge=0, le=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]

_SEMANTIC_VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemanticVersion(ContractModel):
    """Structured Semantic Version 2.0 value with deterministic precedence."""

    major: int = Field(ge=0, description="Backward-incompatible version component.")
    minor: int = Field(ge=0, description="Backward-compatible feature component.")
    patch: int = Field(ge=0, description="Backward-compatible correction component.")
    prerelease: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Ordered prerelease identifiers excluded from stable precedence.",
    )
    build_metadata: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Build identifiers that do not affect precedence.",
    )

    @field_validator("prerelease")
    @classmethod
    def validate_prerelease_identifiers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Enforce prerelease syntax and numeric leading-zero semantics."""

        if any(not re.fullmatch(r"[0-9A-Za-z-]+", item) for item in value):
            raise ValueError("semantic-version identifiers contain invalid characters")
        if any(item.isdigit() and len(item) > 1 and item.startswith("0") for item in value):
            raise ValueError("numeric semantic-version identifiers must not contain leading zeroes")
        return value

    @field_validator("build_metadata")
    @classmethod
    def validate_build_identifiers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Enforce build-metadata syntax without altering SemVer precedence."""

        if any(not re.fullmatch(r"[0-9A-Za-z-]+", item) for item in value):
            raise ValueError("semantic-version identifiers contain invalid characters")
        return value

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a complete Semantic Version string or raise ``ValueError``."""

        match = _SEMANTIC_VERSION_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(f"invalid semantic version: {value}")
        prerelease = tuple((match.group("prerelease") or "").split("."))
        build = tuple((match.group("build") or "").split("."))
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=tuple(item for item in prerelease if item),
            build_metadata=tuple(item for item in build if item),
        )

    def compare_precedence(self, other: Self) -> int:
        """Return negative, zero, or positive according to Semantic Version precedence."""

        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return -1 if core < other_core else 1
        if not self.prerelease and not other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1
        for left, right in zip(self.prerelease, other.prerelease, strict=False):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return -1 if int(left) < int(right) else 1
            if left.isdigit() != right.isdigit():
                return -1 if left.isdigit() else 1
            return -1 if left < right else 1
        if len(self.prerelease) == len(other.prerelease):
            return 0
        return -1 if len(self.prerelease) < len(other.prerelease) else 1

    def __str__(self) -> str:
        """Render the canonical Semantic Version string."""

        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += f"-{'.'.join(self.prerelease)}"
        if self.build_metadata:
            value += f"+{'.'.join(self.build_metadata)}"
        return value


class FeatureReference(ContractModel):
    """Exact immutable reference to one semantic feature definition."""

    feature_id: FeatureId = Field(description="Stable feature identifier.")
    version: SemanticVersion = Field(description="Exact definition version.")


class RegistryReference(ContractModel):
    """Content-addressed reference to one immutable feature-registry snapshot."""

    registry_id: UUID = Field(description="Stable registry lineage identifier.")
    version: SemanticVersion = Field(description="Registry snapshot version.")
    snapshot_hash: Sha256Digest = Field(description="Canonical registry snapshot digest.")


class LanguageApplicability(ContractModel):
    """Explicit language support without wildcard magic strings."""

    all_languages: bool = Field(description="Whether the definition is language-independent.")
    languages: tuple[LanguageTag, ...] = Field(description="Supported BCP 47 language tags.")

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        """Require either an explicit set or an explicit all-languages declaration."""

        if self.all_languages and self.languages:
            raise ValueError("all-language applicability must not enumerate languages")
        if not self.all_languages and not self.languages:
            raise ValueError("language applicability requires at least one language")
        if len(self.languages) != len(set(self.languages)):
            raise ValueError("supported languages must be unique")
        return self


class PlatformApplicability(ContractModel):
    """Explicit platform support without overloaded null or wildcard values."""

    all_platforms: bool = Field(description="Whether the definition applies to every platform.")
    platforms: tuple[Platform, ...] = Field(description="Explicitly supported platforms.")

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        """Require either an explicit set or an explicit all-platform declaration."""

        if self.all_platforms and self.platforms:
            raise ValueError("all-platform applicability must not enumerate platforms")
        if not self.all_platforms and not self.platforms:
            raise ValueError("platform applicability requires at least one platform")
        if len(self.platforms) != len(set(self.platforms)):
            raise ValueError("supported platforms must be unique")
        return self


class TimeRange(ContractModel):
    """Closed-open effective interval used by policies and contextual components."""

    starts_at: UtcDatetime = Field(description="Inclusive UTC start time.")
    ends_at: UtcDatetime | None = Field(default=None, description="Exclusive UTC end time.")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Reject empty or reversed effective intervals."""

        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("time range end must be later than its start")
        return self

    def contains(self, instant: datetime) -> bool:
        """Return whether a timezone-aware instant belongs to the interval."""

        normalized = normalize_utc_datetime(instant)
        return self.starts_at <= normalized and (self.ends_at is None or normalized < self.ends_at)


class VoiceContext(ContractModel):
    """Typed context key used to scope observations and HVM components."""

    language: LanguageTag = Field(description="Language/register model language.")
    platform: Platform | None = Field(default=None, description="Requested or observed platform.")
    content_form: DocumentType | None = Field(
        default=None, description="Canonical content form when known."
    )
    audience: NonEmptyStr | None = Field(default=None, description="Governed audience class.")
    mode: NonEmptyStr | None = Field(default=None, description="Governed communication mode.")
    time_regime: NonEmptyStr | None = Field(
        default=None, description="Named temporal regime when applicable."
    )

    def is_conditioned(self) -> bool:
        """Return whether the context is narrower than a language-only core."""

        return any(
            value is not None
            for value in (
                self.platform,
                self.content_form,
                self.audience,
                self.mode,
                self.time_regime,
            )
        )


class ProducerReference(ContractModel):
    """Versioned producer lineage for an observation without producer implementation details."""

    producer_id: NonEmptyStr = Field(description="Stable extractor, model, prompt, or rubric ID.")
    producer_type: ProducerType = Field(description="Class of producer.")
    version: SemanticVersion = Field(description="Exact producer version.")
    configuration_hash: Sha256Digest = Field(description="Canonical producer configuration hash.")
    calibration_version: SemanticVersion | None = Field(
        default=None, description="Calibration artifact version when applicable."
    )
    actor_id: UUID | None = Field(
        default=None, description="Human actor for reviewed observations when applicable."
    )


class BaselineReference(ContractModel):
    """Reference to the versioned cohort or platform baseline used for a residual."""

    baseline_id: UUID = Field(description="Stable baseline artifact identifier.")
    version: SemanticVersion = Field(description="Exact baseline version.")
    cohort_definition_hash: Sha256Digest = Field(description="Comparison-cohort definition hash.")
