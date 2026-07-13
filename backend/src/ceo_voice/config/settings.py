"""Strongly typed, environment-driven application settings."""

from functools import lru_cache
from typing import Self

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from ceo_voice.core.constants import DEFAULT_SERVICE_NAME, Environment, LogFormat, LogLevel
from ceo_voice.core.exceptions import ConfigurationError


class ApplicationSettings(BaseModel):
    """Process identity and environment controls."""

    service_name: str = Field(
        default=DEFAULT_SERVICE_NAME,
        min_length=1,
        description="Stable service identifier included in logs and telemetry.",
    )
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Runtime environment used to select safety policies.",
    )
    debug: bool = Field(
        default=False,
        description="Whether developer diagnostics are enabled; forbidden in production.",
    )


class LoggingSettings(BaseModel):
    """Central logging behavior."""

    level: LogLevel = Field(default=LogLevel.INFO, description="Minimum emitted log level.")
    format: LogFormat = Field(
        default=LogFormat.CONSOLE,
        description="Human-readable console or machine-readable JSON output.",
    )


class ModelSettings(BaseModel):
    """Provider-neutral model configuration reserved for later AI integrations.

    No provider SDK or model is selected in this phase. The contract prevents future modules
    from reading ad-hoc environment variables or embedding credentials in code.
    """

    enabled: bool = Field(
        default=False,
        description="Whether model-backed capabilities may be initialized.",
    )
    provider: str | None = Field(
        default=None,
        min_length=1,
        description="Configured model provider identifier, without provider-specific behavior.",
    )
    generation_model: str | None = Field(
        default=None,
        min_length=1,
        description="Provider model identifier used for future generation workloads.",
    )
    embedding_model: str | None = Field(
        default=None,
        min_length=1,
        description="Provider model identifier used for future embedding workloads.",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="Provider credential loaded only from an external configuration source.",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
        description="Upper bound for a future provider request.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry count available to a future provider adapter.",
    )

    @model_validator(mode="after")
    def validate_enabled_configuration(self) -> Self:
        """Require a complete minimum configuration when model access is enabled."""

        if not self.enabled:
            return self

        missing = [
            name
            for name, value in (
                ("provider", self.provider),
                ("generation_model", self.generation_model),
                ("api_key", self.api_key),
            )
            if value is None
        ]
        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(f"model access is enabled but fields are missing: {missing_fields}")
        return self


class Settings(BaseSettings):
    """Root settings object populated from environment variables and an optional .env file."""

    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CEO_VOICE_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_environment_policy(self) -> Self:
        """Enforce production-safe defaults at configuration load time."""

        if self.application.environment is not Environment.PRODUCTION:
            return self
        if self.application.debug:
            raise ValueError("debug mode must be disabled in production")
        if self.logging.format is not LogFormat.JSON:
            raise ValueError("JSON logging is required in production")
        return self


def load_settings() -> Settings:
    """Load settings and translate validation details into the application error contract."""

    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(
            "Application configuration is invalid.",
            details={"errors": exc.errors(include_url=False, include_input=False)},
        ) from exc
    except SettingsError as exc:
        raise ConfigurationError(
            "Application configuration could not be loaded.",
            details={"reason": str(exc)},
        ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton after first validated load."""

    return load_settings()


def clear_settings_cache() -> None:
    """Clear cached settings, primarily for isolated tests and controlled reloads."""

    get_settings.cache_clear()
