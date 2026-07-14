"""Declarative feature-definition contracts for the HVM registry."""

from typing import Self

from pydantic import Field, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr
from ceo_voice.voice.enums import (
    ConfidenceComponent,
    DownstreamPermission,
    EvidenceRole,
    EvidenceUnitType,
    FeatureValueType,
    MeasurementClass,
    SourceModality,
    VoiceDimension,
)
from ceo_voice.voice.primitives import (
    FeatureId,
    FeatureReference,
    LanguageApplicability,
    PlatformApplicability,
    SemanticVersion,
)


class ConfidenceModelDefinition(ContractModel):
    """Versioned contract for confidence estimation and calibration."""

    model_id: NonEmptyStr = Field(description="Stable confidence-model contract identifier.")
    version: SemanticVersion = Field(description="Exact confidence-model contract version.")
    required_components: tuple[ConfidenceComponent, ...] = Field(
        min_length=1, description="Confidence dimensions the estimator must populate."
    )
    calibration_required: bool = Field(
        description="Whether empirical calibration is required before actionable use."
    )

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        """Reject duplicate confidence dimensions."""

        if len(self.required_components) != len(set(self.required_components)):
            raise ValueError("confidence components must be unique")
        return self


class AggregationStrategyReference(ContractModel):
    """Versioned strategy contract selected declaratively by a feature definition."""

    strategy_id: NonEmptyStr = Field(description="Stable aggregation strategy identifier.")
    version: SemanticVersion = Field(description="Exact aggregation contract version.")
    output_value_type: FeatureValueType = Field(description="Required aggregate value type.")


class EvidenceRequirements(ContractModel):
    """Structural evidence gates required before a feature may be promoted."""

    minimum_evidence_units: int = Field(
        ge=1, description="Minimum addressable evidence-unit count."
    )
    minimum_independent_clusters: int = Field(
        ge=1, description="Minimum support after duplicate/campaign grouping."
    )
    required_roles: tuple[EvidenceRole, ...] = Field(
        min_length=1, description="Evidence roles required by the definition."
    )
    allowed_modalities: tuple[SourceModality, ...] = Field(
        min_length=1, description="Source modalities admissible for the feature."
    )
    requires_target_attribution: bool = Field(
        description="Whether target-authorship attribution is a hard gate."
    )
    requires_rights_admissibility: bool = Field(
        description="Whether downstream rights admissibility is a hard gate."
    )

    @model_validator(mode="after")
    def validate_requirements(self) -> Self:
        """Keep role and modality requirements unambiguous."""

        if len(self.required_roles) != len(set(self.required_roles)):
            raise ValueError("required evidence roles must be unique")
        if len(self.allowed_modalities) != len(set(self.allowed_modalities)):
            raise ValueError("allowed evidence modalities must be unique")
        if self.minimum_independent_clusters > self.minimum_evidence_units:
            raise ValueError("independent-cluster minimum cannot exceed evidence-unit minimum")
        return self


class FeatureDefinition(ContractModel):
    """Immutable semantic definition for one observable writing behavior.

    Definitions contain no extractor, estimator, or model implementation. New features are added
    by registering another validated definition and wiring compatible implementations to the
    referenced contracts.
    """

    feature_id: FeatureId = Field(description="Stable machine-readable feature identifier.")
    semantic_version: SemanticVersion = Field(description="Definition semantic version.")
    display_name: NonEmptyStr = Field(description="Human-readable feature name.")
    description: NonEmptyStr = Field(description="Observable phenomenon represented.")
    dimension: VoiceDimension = Field(description="Independent HVM dimension.")
    observation_scope: EvidenceUnitType = Field(description="Unit at which observations exist.")
    opportunity_unit: NonEmptyStr = Field(description="Denominator or opportunity semantics.")
    measurement_pipeline: tuple[MeasurementClass, ...] = Field(
        min_length=1, description="Ordered measurement-class signature."
    )
    supported_languages: LanguageApplicability = Field(
        description="Explicit language applicability."
    )
    supported_platforms: PlatformApplicability = Field(
        description="Explicit platform applicability."
    )
    supported_modalities: tuple[SourceModality, ...] = Field(
        min_length=1, description="Modalities in which the feature is meaningful."
    )
    value_type: FeatureValueType = Field(description="Required typed value representation.")
    confidence_model: ConfidenceModelDefinition = Field(
        description="Confidence estimation contract."
    )
    aggregation_strategy: AggregationStrategyReference = Field(
        description="Aggregation contract used for this feature."
    )
    downstream_permissions: tuple[DownstreamPermission, ...] = Field(
        min_length=1, description="Explicitly allowed downstream uses."
    )
    evidence_requirements: EvidenceRequirements = Field(
        description="Evidence gates for profile promotion."
    )
    nuisance_controls: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Named nuisance variables required during estimation or validation.",
    )
    minimum_text_characters: int = Field(
        ge=1, description="Minimum evidence-unit size for a meaningful observation."
    )

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        """Enforce compatibility among the definition's declarative contracts."""

        if len(self.measurement_pipeline) != len(set(self.measurement_pipeline)):
            raise ValueError("measurement pipeline classes must be unique")
        if len(self.supported_modalities) != len(set(self.supported_modalities)):
            raise ValueError("supported modalities must be unique")
        if len(self.downstream_permissions) != len(set(self.downstream_permissions)):
            raise ValueError("downstream permissions must be unique")
        if len(self.nuisance_controls) != len(set(self.nuisance_controls)):
            raise ValueError("nuisance controls must be unique")
        if self.aggregation_strategy.output_value_type is not self.value_type:
            raise ValueError("aggregation output type must match the feature value type")
        unsupported_modalities = set(self.evidence_requirements.allowed_modalities) - set(
            self.supported_modalities
        )
        if unsupported_modalities:
            raise ValueError("evidence requirements include unsupported modalities")
        return self

    @property
    def reference(self) -> FeatureReference:
        """Return the exact immutable reference used by observations and components."""

        return FeatureReference(feature_id=self.feature_id, version=self.semantic_version)
