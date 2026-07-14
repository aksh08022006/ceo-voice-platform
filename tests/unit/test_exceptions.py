"""Tests for the shared application exception contract."""

import pytest

from ceo_voice.core.exceptions import (
    ApplicationError,
    ApplicationValidationError,
    ConfigurationError,
    ContextCompilationError,
    DataIngestionError,
    EvaluationError,
    ExternalAPIError,
    GenerationError,
    RetrievalError,
    StorageError,
    VoiceProfileError,
)


def test_application_error_has_transport_neutral_shape() -> None:
    error = ApplicationError(
        "Operation failed.",
        details={"operation": "test"},
        retryable=True,
    )

    assert str(error) == "Operation failed."
    assert error.to_dict() == {
        "code": "application_error",
        "message": "Operation failed.",
        "details": {"operation": "test"},
        "retryable": True,
    }


@pytest.mark.parametrize(
    ("exception_type", "expected_code"),
    [
        (ConfigurationError, "configuration_error"),
        (ContextCompilationError, "context_compilation_error"),
        (DataIngestionError, "data_ingestion_error"),
        (RetrievalError, "retrieval_error"),
        (GenerationError, "generation_error"),
        (EvaluationError, "evaluation_error"),
        (VoiceProfileError, "voice_profile_error"),
        (ExternalAPIError, "external_api_error"),
        (StorageError, "storage_error"),
        (ApplicationValidationError, "validation_error"),
    ],
)
def test_exception_subclasses_expose_stable_codes(
    exception_type: type[ApplicationError],
    expected_code: str,
) -> None:
    assert exception_type("failure").code == expected_code
