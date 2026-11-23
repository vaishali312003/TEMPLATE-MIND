"""Application settings.

This is the only module that reads environment variables. All other code obtains configuration
through ``get_settings()`` (usually injected via ``app/api/dependencies.py``).

Secrets are ``SecretStr`` so they never appear in ``repr``, logs or tracebacks.
"""

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigurationError

BYTES_PER_MEGABYTE = 1024 * 1024

# Template formats supported by the product specification (DOCX first, then PDF).
SUPPORTED_TEMPLATE_EXTENSIONS = frozenset({"docx", "pdf"})

_EXTENSION_PATTERN = re.compile(r"^[a-z0-9]+$")
_ORIGIN_PATTERN = re.compile(r"^(\*|https?://[^/\s]+)$")
_DATABASE_URL_PATTERN = re.compile(r"^postgresql(\+[a-z0-9_]+)?://", re.IGNORECASE)

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
CommaSeparatedList = Annotated[list[str], NoDecode]


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


def _split_comma_separated(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    # ---- App ----
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    log_level: LogLevel = "INFO"
    cors_allowed_origins: CommaSeparatedList = Field(default_factory=list)

    # ---- Database ----
    database_url: SecretStr

    # ---- LLM ----
    llm_provider: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    llm_model: str = Field(min_length=1)
    llm_api_key: SecretStr
    llm_base_url: AnyHttpUrl | None = None
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    # ---- Embeddings / Vision ----
    embedding_model: str = Field(min_length=1)
    embedding_api_key: SecretStr | None = None
    vision_model: str | None = Field(default=None, min_length=1)

    # ---- OCR ----
    ocr_engine: Literal["paddleocr", "tesseract"]

    # ---- Storage ----
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: Path = Path("data/storage")
    s3_endpoint_url: AnyHttpUrl | None = None
    s3_bucket: str | None = Field(default=None, min_length=1)
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # ---- LibreOffice ----
    libreoffice_binary_path: str = Field(default="soffice", min_length=1)
    libreoffice_timeout_seconds: int = Field(default=120, ge=1)

    # ---- Upload limits ----
    max_upload_size_mb: int = Field(default=25, ge=1)
    allowed_template_extensions: CommaSeparatedList = Field(default_factory=lambda: ["docx", "pdf"])
    allowed_event_file_extensions: CommaSeparatedList = Field(
        default_factory=lambda: ["docx", "pdf", "xlsx", "csv", "jpg", "jpeg", "png"]
    )

    # ---------------------------------------------------------------- normalisation (before)

    @field_validator("app_env", "llm_provider", "ocr_engine", "storage_backend", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator(
        "cors_allowed_origins",
        "allowed_template_extensions",
        "allowed_event_file_extensions",
        mode="before",
    )
    @classmethod
    def _parse_comma_separated(cls, value: object) -> object:
        return _split_comma_separated(value)

    # --------------------------------------------------------------------- validation (after)

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_origins(cls, value: list[str]) -> list[str]:
        if any(not _ORIGIN_PATTERN.match(origin) for origin in value):
            raise ValueError(
                "origins must be '*' or http(s)://host[:port] without a path or trailing slash"
            )
        return list(dict.fromkeys(value))

    @field_validator("allowed_template_extensions", "allowed_event_file_extensions")
    @classmethod
    def _normalize_extensions(cls, value: list[str]) -> list[str]:
        normalized = [item.lstrip(".").lower() for item in value]
        if not normalized:
            raise ValueError("at least one extension is required")
        if any(not _EXTENSION_PATTERN.match(item) for item in normalized):
            raise ValueError("extensions may contain only letters and digits")
        return list(dict.fromkeys(normalized))

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        if not _DATABASE_URL_PATTERN.match(value.get_secret_value().strip()):
            raise ValueError(
                "must be a PostgreSQL URL starting with postgresql:// or postgresql+<driver>://"
            )
        return value

    @field_validator(
        "database_url",
        "llm_api_key",
        "embedding_api_key",
        "s3_access_key_id",
        "s3_secret_access_key",
    )
    @classmethod
    def _secret_not_blank(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_cross_field_rules(self) -> Self:
        if self.storage_backend == "s3":
            required = {
                "S3_ENDPOINT_URL": self.s3_endpoint_url,
                "S3_BUCKET": self.s3_bucket,
                "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError("required when STORAGE_BACKEND=s3: " + ", ".join(missing))

        if self.app_env is AppEnvironment.PRODUCTION and "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*' in production")

        unsupported = sorted(set(self.allowed_template_extensions) - SUPPORTED_TEMPLATE_EXTENSIONS)
        if unsupported:
            raise ValueError(
                "ALLOWED_TEMPLATE_EXTENSIONS supports only docx and pdf, got: "
                + ", ".join(unsupported)
            )
        return self

    # ------------------------------------------------------------------------- conveniences

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnvironment.PRODUCTION

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * BYTES_PER_MEGABYTE


def _describe_validation_error(error: ValidationError) -> list[dict[str, str]]:
    """Reduce a pydantic error to variable name + problem, never echoing input values."""
    problems: list[dict[str, str]] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location = item["loc"]
        variable = str(location[0]).upper() if location else "SETTINGS"
        problems.append({"variable": variable, "problem": item["msg"]})
    return problems


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings; fail fast with a ``ConfigurationError`` that leaks no secrets."""
    try:
        # Required fields are populated from the environment by pydantic-settings; static type
        # checkers only see them as constructor parameters.
        return Settings()  # type: ignore[call-arg]
    except ValidationError as error:
        problems = _describe_validation_error(error)
        summary = "; ".join(f"{p['variable']}: {p['problem']}" for p in problems)
        # "from None": the original error text contains the rejected input values, which may
        # be secrets (for example a malformed DATABASE_URL with a password).
        raise ConfigurationError(
            f"Invalid configuration: {summary}", details={"problems": problems}
        ) from None
