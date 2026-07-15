"""Tests for environment-driven configuration and safety policies."""

import pytest
from pydantic import SecretStr, ValidationError

from ceo_voice.config import ModelSettings, Settings, get_settings, load_settings
from ceo_voice.core.constants import Environment, LogFormat, LogLevel
from ceo_voice.core.exceptions import ConfigurationError


def test_defaults_are_safe_for_local_foundation_work() -> None:
    settings = Settings(_env_file=None)

    assert settings.application.environment is Environment.DEVELOPMENT
    assert settings.application.debug is False
    assert settings.logging.level is LogLevel.INFO
    assert settings.model.enabled is False
    assert settings.model.api_key is None


def test_nested_environment_variables_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEO_VOICE_APPLICATION__ENVIRONMENT", "production")
    monkeypatch.setenv("CEO_VOICE_LOGGING__FORMAT", "json")
    monkeypatch.setenv("CEO_VOICE_LOGGING__LEVEL", "WARNING")

    settings = Settings(_env_file=None)

    assert settings.application.environment is Environment.PRODUCTION
    assert settings.logging.format is LogFormat.JSON
    assert settings.logging.level is LogLevel.WARNING


def test_production_rejects_debug_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEO_VOICE_APPLICATION__ENVIRONMENT", "production")
    monkeypatch.setenv("CEO_VOICE_APPLICATION__DEBUG", "true")
    monkeypatch.setenv("CEO_VOICE_LOGGING__FORMAT", "json")

    with pytest.raises(ValidationError, match="debug mode must be disabled"):
        Settings(_env_file=None)


def test_production_requires_json_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEO_VOICE_APPLICATION__ENVIRONMENT", "production")

    with pytest.raises(ConfigurationError) as captured:
        load_settings()

    assert captured.value.code == "configuration_error"
    assert captured.value.details["errors"]


def test_malformed_nested_environment_value_is_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CEO_VOICE_APPLICATION", "not-json")

    with pytest.raises(ConfigurationError) as captured:
        load_settings()

    assert captured.value.message == "Application configuration could not be loaded."
    assert "application" in str(captured.value.details["reason"])


def test_enabled_model_configuration_requires_minimum_fields() -> None:
    with pytest.raises(ValidationError, match="generation_model, api_key"):
        ModelSettings(enabled=True, provider="provider")


def test_enabled_model_configuration_keeps_api_key_secret() -> None:
    model = ModelSettings(
        enabled=True,
        provider="provider",
        generation_model="generation-model",
        api_key=SecretStr("not-a-real-key"),
    )

    assert model.api_key is not None
    assert str(model.api_key) == "**********"
    assert model.api_key.get_secret_value() == "not-a-real-key"


def test_enabled_model_configuration_validates_token_budget() -> None:
    with pytest.raises(ValidationError, match="smaller than the context window"):
        ModelSettings(
            enabled=True,
            provider="openai",
            generation_model="model",
            api_key=SecretStr("secret"),
            context_window_tokens=512,
            maximum_output_tokens=512,
        )


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
