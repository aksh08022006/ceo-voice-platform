"""Closed vocabularies for the Hierarchical Voice Model domain."""

from enum import StrEnum


class VoiceDimension(StrEnum):
    """Independent representational dimensions defined by the HVM research contract."""

    ORTHOGRAPHIC = "orthographic"
    LAYOUT = "layout"
    LEXICAL = "lexical"
    MORPHOLOGICAL = "morphological"
    SYNTACTIC = "syntactic"
    RHYTHMIC = "rhythmic"
    SEMANTIC_EXPRESSION = "semantic_expression"
    DISCOURSE_RHETORICAL = "discourse_rhetorical"
    PRAGMATIC_STANCE = "pragmatic_stance"
    NARRATIVE_PERSPECTIVE = "narrative_perspective"
    AUDIENCE_INTERPERSONAL = "audience_interpersonal"
    REASONING_ARGUMENT = "reasoning_argument"
    EDITORIAL_REVISION = "editorial_revision"
    NEGATIVE_SPACE = "negative_space"
    PLATFORM_ADAPTATION = "platform_adaptation"
    TEMPORAL_DRIFT = "temporal_drift"
    INTERACTION_COVARIANCE = "interaction_covariance"
    NUISANCE_CONTROL = "nuisance_control"


class MeasurementClass(StrEnum):
    """Method class that produced or transformed an observation."""

    DETERMINISTIC = "deterministic"
    STATISTICAL = "statistical"
    PROBABILISTIC = "probabilistic"
    LLM_DERIVED = "llm_derived"
    HUMAN_ANNOTATED = "human_annotated"


class FeatureValueType(StrEnum):
    """Supported typed value representations for definitions and observations."""

    SCALAR = "scalar"
    CONTINUOUS_DISTRIBUTION = "continuous_distribution"
    CATEGORICAL_DISTRIBUTION = "categorical_distribution"
    COUNT_DISTRIBUTION = "count_distribution"
    SEQUENCE_MODEL = "sequence_model"
    SPARSE_VECTOR = "sparse_vector"
    GRAPH = "graph"
    INTERVAL = "interval"
    MIXTURE = "mixture"
    PROTOTYPE_SET = "prototype_set"


class ConfidenceComponent(StrEnum):
    """Independent confidence dimensions that must remain explainable."""

    MEASUREMENT_RELIABILITY = "measurement_reliability"
    ATTRIBUTION_RELIABILITY = "attribution_reliability"
    COVERAGE = "coverage"
    EFFECTIVE_SUPPORT = "effective_support"
    CONTEXT_DIVERSITY = "context_diversity"
    STABILITY = "stability"
    CROSS_CONTEXT_ROBUSTNESS = "cross_context_robustness"
    NUISANCE_ROBUSTNESS = "nuisance_robustness"
    DISTINCTIVENESS = "distinctiveness"
    FRESHNESS = "freshness"
    CALIBRATION = "calibration"
    CONFLICT = "conflict"


class DownstreamPermission(StrEnum):
    """Uses for which a feature definition may be consumed."""

    EXPLORE = "explore"
    RETRIEVE = "retrieve"
    GENERATE = "generate"
    CRITIQUE = "critique"
    EVALUATE = "evaluate"
    EXPLAIN = "explain"


class EvidenceRole(StrEnum):
    """Relationship of an evidence unit to a voice assertion."""

    SUPPORT = "support"
    COUNTEREVIDENCE = "counterevidence"
    OPPORTUNITY = "opportunity"
    PROTOTYPE = "prototype"
    ANTI_PROTOTYPE = "anti_prototype"
    EXCEPTION = "exception"


class EvidenceUnitType(StrEnum):
    """Addressable structural unit within an immutable document version."""

    DOCUMENT = "document"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    RHETORICAL_UNIT = "rhetorical_unit"
    REVISION_HUNK = "revision_hunk"
    WINDOW = "window"


class SourceModality(StrEnum):
    """Production modality used to govern feature admissibility."""

    AUTHORED_WRITTEN = "authored_written"
    PREPARED_SPOKEN = "prepared_spoken"
    SPONTANEOUS_SPOKEN = "spontaneous_spoken"
    INTERVIEW_MEDIATED = "interview_mediated"
    MACHINE_TRANSCRIPT = "machine_transcript"
    TRANSLATED = "translated"


class TargetIdentityType(StrEnum):
    """Governed identity whose expression the HVM represents."""

    PERSONAL_AUTHORSHIP = "personal_authorship"
    APPROVED_EXECUTIVE_BRAND = "approved_executive_brand"
    EDITORIAL_TEAM_VOICE = "editorial_team_voice"


class ObservationState(StrEnum):
    """Whether an observation contains a value or an explicit non-value."""

    OBSERVED = "observed"
    ABSTAINED = "abstained"
    MISSING = "missing"


class ProducerType(StrEnum):
    """Class of actor or system that created an observation."""

    DETERMINISTIC_SYSTEM = "deterministic_system"
    STATISTICAL_SYSTEM = "statistical_system"
    PROBABILISTIC_MODEL = "probabilistic_model"
    LLM_ANNOTATOR = "llm_annotator"
    HUMAN_REVIEWER = "human_reviewer"


class DecisionState(StrEnum):
    """Maximum downstream authority granted to a component."""

    UNSUPPORTED = "unsupported"
    EXPLORATORY = "exploratory"
    DESCRIPTIVE = "descriptive"
    ACTIONABLE_SOFT = "actionable_soft"
    ACTIONABLE_STRONG = "actionable_strong"
    EXPLICIT_POLICY = "explicit_policy"


class InteractionType(StrEnum):
    """Supported structural relationship among voice features."""

    COVARIANCE = "covariance"
    CONDITIONAL_PROBABILITY = "conditional_probability"
    SEQUENTIAL_MOTIF = "sequential_motif"
    CROSS_LAYER = "cross_layer"
    POSITIONAL = "positional"
    CONTEXTUAL = "contextual"
    NONLINEAR = "nonlinear"
    MIXTURE_COMPONENT = "mixture_component"
    EXPLICIT_RULE = "explicit_rule"


class PrototypeKind(StrEnum):
    """Whether a prototype is representative or a scoped counterexample."""

    PROTOTYPE = "prototype"
    ANTI_PROTOTYPE = "anti_prototype"


class CopyRisk(StrEnum):
    """Governed risk of exposing a prototype to downstream consumers."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    PROHIBITED = "prohibited"


class ConstraintSeverity(StrEnum):
    """Enforcement strength of a negative constraint."""

    ADVISORY = "advisory"
    SOFT = "soft"
    HARD = "hard"


class ConstraintBasis(StrEnum):
    """Evidence semantics under which a negative constraint exists."""

    STATISTICAL_AVOIDANCE = "statistical_avoidance"
    EXPLICIT_POLICY = "explicit_policy"


class PreferenceAuthority(StrEnum):
    """Authority under which an explicit preference was recorded."""

    TARGET_LEADER = "target_leader"
    AUTHORIZED_DELEGATE = "authorized_delegate"
    EDITORIAL_POLICY = "editorial_policy"
    COMPLIANCE_POLICY = "compliance_policy"


class DriftStatus(StrEnum):
    """Review state of a possible temporal regime change."""

    STABLE = "stable"
    CANDIDATE = "candidate"
    REVIEW_REQUIRED = "review_required"
    ACCEPTED_REGIME = "accepted_regime"
    REJECTED_CONFOUND = "rejected_confound"


class ReleaseStatus(StrEnum):
    """State derived by replaying immutable release lifecycle events."""

    BUILDING = "building"
    VALIDATING = "validating"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ReleaseEventType(StrEnum):
    """Immutable facts that drive release lifecycle state."""

    CREATED = "created"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    APPROVED = "approved"
    ACTIVATED = "activated"
    SUPERSEDED = "superseded"
    ROLLED_BACK_TO = "rolled_back_to"
    WITHDRAWN = "withdrawn"


class ValidationSeverity(StrEnum):
    """Structural validation issue severity."""

    ERROR = "error"
    WARNING = "warning"


class ValidationCode(StrEnum):
    """Stable machine-readable structural validation outcomes."""

    SCHEMA_INTEGRITY = "schema_integrity"
    EVIDENCE_COMPLETENESS = "evidence_completeness"
    REFERENCE_INTEGRITY = "reference_integrity"
    VERSION_CONSISTENCY = "version_consistency"
    CONFIDENCE_COMPLETENESS = "confidence_completeness"
    FEATURE_REGISTRY_CONSISTENCY = "feature_registry_consistency"
    TENANT_IDENTITY_CONSISTENCY = "tenant_identity_consistency"


class RetrievalProjectionType(StrEnum):
    """Rebuildable query projection over one sealed HVM release."""

    FEATURE_INDEX = "feature_index"
    INTERACTION_ADJACENCY = "interaction_adjacency"
    SEQUENCE_INDEX = "sequence_index"
    CONSTRAINT_INDEX = "constraint_index"
    PROTOTYPE_INDEX = "prototype_index"
    EVIDENCE_INVERTED_INDEX = "evidence_inverted_index"
    DRIFT_REVIEW_INDEX = "drift_review_index"


class VoiceQueryKind(StrEnum):
    """Stable query intents supported by future retrieval implementations."""

    OPENING_STYLE = "opening_style"
    CLOSING_STYLE = "closing_style"
    LEXICAL_FEATURES = "lexical_features"
    RHETORICAL_FEATURES = "rhetorical_features"
    PLATFORM_ADAPTATIONS = "platform_adaptations"
    FEATURES = "features"


class ResolvedComponentKind(StrEnum):
    """Public component categories returned by a voice-profile query."""

    CORE_RESIDUAL = "core_residual"
    CONDITIONAL_RESIDUAL = "conditional_residual"
    INTERACTION = "interaction"
    NEGATIVE_CONSTRAINT = "negative_constraint"
    EXPLICIT_PREFERENCE = "explicit_preference"
    PROTOTYPE = "prototype"


class ResolutionSource(StrEnum):
    """Feature-level inheritance source selected during future retrieval."""

    EXPLICIT_POLICY = "explicit_policy"
    CONDITIONAL_RESIDUAL = "conditional_residual"
    CORE_RESIDUAL = "core_residual"
    PLATFORM_BASELINE = "platform_baseline"
    NEUTRAL_FALLBACK = "neutral_fallback"


class VectorNormalization(StrEnum):
    """Declared normalization semantics for sparse vector values."""

    NONE = "none"
    L1 = "l1"
    L2 = "l2"
    Z_SCORE = "z_score"
