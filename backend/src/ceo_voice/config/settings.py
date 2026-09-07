"""Strongly typed, environment-driven application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

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


class ApiSettings(BaseModel):
    """HTTP delivery settings for the browser-facing application."""

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    allowed_origins: tuple[str, ...] = Field(
        default=("http://localhost:3000", "http://127.0.0.1:3000"),
        description="Exact browser origins allowed to call the API.",
    )
    showcase_enabled: bool = Field(
        default=True,
        description="Enable synthetic, explicitly non-production walkthrough profiles.",
    )
    published_profile_catalog: Path | None = Field(
        default=None,
        description="Validated immutable profile catalog served instead of showcase fixtures.",
    )
    continuation_key: SecretStr | None = Field(
        default=None,
        description="Fernet key for encrypted browser-held workflow continuation across instances.",
    )
    continuation_ttl_seconds: int = Field(default=604800, ge=60, le=2592000)
    artifact_storage: Literal["memory", "filesystem"] = Field(
        default="memory",
        description="HTTP workflows retain artifacts in memory; filesystem is an explicit local diagnostic opt-in.",
    )


class ModelSettings(BaseModel):
    """Provider-neutral model configuration for generation and optional embeddings.

    The contract prevents consumers from reading ad-hoc environment variables or embedding
    credentials in code.
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
        description="Provider model identifier used for generation workloads.",
    )
    gemini_thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Optional Gemini reasoning level; omitted preserves provider defaults.",
    )
    embedding_model: str | None = Field(
        default=None,
        min_length=1,
        description="Provider model identifier used for explicitly enabled hybrid retrieval.",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="Provider credential loaded only from an external configuration source.",
    )
    base_url: str | None = Field(
        default=None,
        min_length=1,
        description="Optional provider-compatible API base URL for controlled deployments.",
    )
    context_window_tokens: int = Field(
        default=30_000,
        ge=512,
        description="Context window enforced by the prompt budget manager.",
    )
    maximum_output_tokens: int = Field(
        default=800,
        ge=32,
        description="Maximum generated tokens requested from the provider.",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
        description="Upper bound for one provider request.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry count available to the configured provider adapter.",
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
        if self.maximum_output_tokens >= self.context_window_tokens:
            raise ValueError("maximum output tokens must be smaller than the context window")
        return self


class RetrievalSettings(BaseModel):
    """Explicit experiment selection and bounded embedding preparation settings."""

    mode: Literal["baseline", "bm25", "hybrid"] = "baseline"
    relevance_weight: float = Field(default=0.35, gt=0, le=0.5, allow_inf_nan=False)
    sparse_weight: float = Field(default=0.5, gt=0, lt=1, allow_inf_nan=False)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    embedding_revision: str | None = Field(default=None, min_length=1)
    embedding_dimensions: int = Field(default=1536, ge=1, le=65536)
    embedding_batch_size: int = Field(default=16, ge=1, le=32)
    maximum_embedding_input_bytes: int = Field(default=8000, ge=1, le=8000)
    maximum_embedding_items: int = Field(default=512, ge=1, le=2048)
    embedding_cache_items: int = Field(default=2048, ge=0, le=10000)


class WorkspaceSettings(BaseModel):
    """Explicit production workspace dependencies; incomplete setup never falls back to anonymous access."""

    enabled: bool = False
    database_url: SecretStr | None = None
    encryption_key: SecretStr | None = None
    workspace_id: str = Field(default="narrative-company", min_length=1, max_length=160)
    workspace_name: str = Field(default="The Narrative Company", min_length=1, max_length=160)
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    bootstrap_admin_emails: tuple[str, ...] = ()
    allowed_profiles: tuple[str, ...] = ("ali-ghodsi", "matei-zaharia")
    maximum_runs_per_hour: int = Field(default=30, ge=1, le=1000)
    run_lease_seconds: int = Field(default=240, ge=60, le=600)
    fidelity_enabled: bool = False
    fidelity_model: str | None = None

    @model_validator(mode="after")
    def production_dependencies(self) -> Self:
        if self.enabled and not all(
            (
                self.database_url,
                self.encryption_key,
                self.auth_issuer,
                self.auth_audience,
                self.auth_jwks_url,
            )
        ):
            raise ValueError(
                "enabled workspace requires database, encryption, and managed authentication"
            )
        if self.enabled and not self.fidelity_enabled:
            raise ValueError("enabled workspace requires claim review")
        if (
            self.enabled
            and self.database_url
            and not self.database_url.get_secret_value().startswith(
                ("postgresql://", "postgres://")
            )
        ):
            raise ValueError(
                "production workspace requires PostgreSQL, never an ephemeral SQLite file"
            )
        for value in (self.auth_issuer, self.auth_audience, self.auth_jwks_url):
            if value and not value.startswith("https://"):
                raise ValueError("managed authentication endpoints must use HTTPS")
        return self


class Settings(BaseSettings):
    """Root settings object populated from environment variables and an optional .env file."""

    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        env_prefix="CEO_VOICE_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_environment_policy(self) -> Self:
        """Enforce production-safe defaults at configuration load time."""

        if self.retrieval.mode == "hybrid" and (
            not self.model.enabled
            or self.model.provider is None
            or self.model.provider.lower() != "openai"
            or not self.model.embedding_model
            or not self.retrieval.embedding_revision
        ):
            raise ValueError(
                "hybrid retrieval requires enabled OpenAI-compatible model access, "
                "an embedding model and an explicit embedding revision"
            )
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
