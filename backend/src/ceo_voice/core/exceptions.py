"""Application exception hierarchy.

Domain and infrastructure layers raise these exceptions at their boundaries. The hierarchy
lets a future transport layer convert failures to HTTP, queue, or workflow responses without
coupling those layers to implementation-specific exceptions.
"""

from collections.abc import Mapping


class ApplicationError(Exception):
    """Base class for expected application failures.

    Args:
        message: Safe, human-readable description of the failure.
        details: Structured diagnostic context. Secrets and personal data must not be included.
        retryable: Whether an orchestrator may safely retry the failed operation.
    """

    code = "application_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        self.retryable = retryable

    def to_dict(self) -> dict[str, object]:
        """Return a transport-neutral, serializable representation of the error."""

        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


class ConfigurationError(ApplicationError):
    """Raised when application configuration is missing or invalid."""

    code = "configuration_error"


class DataIngestionError(ApplicationError):
    """Raised when source data cannot be accepted or normalized."""

    code = "data_ingestion_error"


class RetrievalError(ApplicationError):
    """Raised when a retrieval operation cannot produce a valid context."""

    code = "retrieval_error"


class GenerationError(ApplicationError):
    """Raised when content generation fails or returns an invalid result."""

    code = "generation_error"


class ContextCompilationError(ApplicationError):
    """Raised when governed artifacts cannot form a safe generation context."""

    code = "context_compilation_error"


class EvaluationError(ApplicationError):
    """Raised when a candidate cannot be evaluated reliably."""

    code = "evaluation_error"


class ViralityError(ApplicationError):
    """Raised when structural engagement intelligence cannot be produced safely."""

    code = "virality_error"


class ViralityValidationError(ViralityError):
    """Raised when a Virality Knowledge Release violates mandatory invariants."""

    code = "virality_validation_error"


class VoiceProfileError(ApplicationError):
    """Raised when a voice profile cannot be created, loaded, or validated."""

    code = "voice_profile_error"


class FeatureRegistryError(VoiceProfileError):
    """Raised when a feature registry reference is missing, ambiguous, or incompatible."""

    code = "feature_registry_error"


class VoiceAnalysisError(VoiceProfileError):
    """Raised when a clean document cannot be analyzed safely."""

    code = "voice_analysis_error"


class AnalyzerRegistrationError(VoiceAnalysisError):
    """Raised when analyzer registration is ambiguous or incompatible."""

    code = "analyzer_registration_error"


class AnalyzerDependencyError(VoiceAnalysisError):
    """Raised when an analyzer dependency graph cannot be scheduled."""

    code = "analyzer_dependency_error"


class ObservationBuildError(VoiceAnalysisError):
    """Raised when a measurement cannot become a valid HVM observation."""

    code = "observation_build_error"


class ProfileBuildError(VoiceProfileError):
    """Raised when a corpus cannot produce or publish a valid profile release."""

    code = "profile_build_error"


class HVMValidationError(VoiceProfileError):
    """Raised when an HVM candidate fails mandatory structural validation."""

    code = "hvm_validation_error"


class ProfileCompilationError(VoiceProfileError):
    """Raised when injected profile-compilation stages violate their contracts."""

    code = "profile_compilation_error"


class ReleaseLifecycleError(VoiceProfileError):
    """Raised when an immutable release receives an invalid lifecycle transition."""

    code = "release_lifecycle_error"


class ExternalAPIError(ApplicationError):
    """Raised when a third-party dependency fails or violates its contract."""

    code = "external_api_error"


class StorageError(ApplicationError):
    """Raised when durable or vector storage cannot complete an operation."""

    code = "storage_error"


class ApplicationValidationError(ApplicationError):
    """Raised when data crosses an application boundary in an invalid shape."""

    code = "validation_error"
