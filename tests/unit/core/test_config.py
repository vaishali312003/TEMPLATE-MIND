from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BYTES_PER_MEGABYTE, AppEnvironment, Settings, get_settings
from app.core.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_VARIABLES = [
    "DATABASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_KEY",
    "EMBEDDING_MODEL",
    "OCR_ENGINE",
]
SECRET_VARIABLES = [
    "DATABASE_URL",
    "LLM_API_KEY",
    "EMBEDDING_API_KEY",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
]


def load() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def read_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        assert separator == "=", f"malformed line in .env.example: {line!r}"
        values[key.strip()] = value.strip()
    return values


# ------------------------------------------------------------------------------ defaults


def test_defaults_when_only_required_values_are_set(required_env: dict[str, str]) -> None:
    settings = load()

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.is_production is False
    assert settings.log_level == "INFO"
    assert settings.cors_allowed_origins == []
    assert settings.storage_backend == "local"
    assert settings.storage_local_path == Path("data/storage")
    assert settings.max_upload_size_bytes == 25 * BYTES_PER_MEGABYTE
    assert settings.allowed_template_extensions == ["docx", "pdf"]
    assert settings.allowed_event_file_extensions == [
        "docx",
        "pdf",
        "xlsx",
        "csv",
        "jpg",
        "jpeg",
        "png",
    ]
    assert settings.libreoffice_binary_path == "soffice"
    assert settings.libreoffice_timeout_seconds == 120
    assert settings.llm_timeout_seconds == 60
    assert settings.llm_max_retries == 2
    assert settings.llm_base_url is None
    assert settings.embedding_api_key is None
    assert settings.vision_model is None


def test_secrets_are_masked_in_repr_and_str(required_env: dict[str, str]) -> None:
    settings = load()
    rendered = repr(settings) + str(settings)

    assert "test-llm-key" not in rendered
    assert "test-password" not in rendered
    assert settings.llm_api_key.get_secret_value() == "test-llm-key"


# --------------------------------------------------------------------- required variables


@pytest.mark.parametrize("variable", REQUIRED_VARIABLES)
def test_missing_required_variable_fails(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.delenv(variable)

    with pytest.raises(ValidationError) as exc_info:
        load()

    assert variable.lower() in str(exc_info.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_value_is_rejected_as_missing(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    monkeypatch.setenv("LLM_MODEL", blank)

    with pytest.raises(ValidationError):
        load()


def test_blank_secret_is_rejected(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_API_KEY", "   ")

    with pytest.raises(ValidationError):
        load()


# --------------------------------------------------------------------------- field rules


@pytest.mark.parametrize(
    "url",
    ["mysql://u:p@h/db", "sqlite:///x.db", "postgres://u:p@h/db", "http://h/db"],
)
def test_database_url_must_be_postgresql(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)

    with pytest.raises(ValidationError):
        load()


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"],
)
def test_database_url_accepts_postgresql_forms(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)

    assert load().database_url.get_secret_value() == url


def test_provider_and_engine_values_are_normalised(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", " Gemini ")
    monkeypatch.setenv("OCR_ENGINE", "PaddleOCR")
    monkeypatch.setenv("APP_ENV", "TEST")

    settings = load()

    assert settings.llm_provider == "gemini"
    assert settings.ocr_engine == "paddleocr"
    assert settings.app_env is AppEnvironment.TEST


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("OCR_ENGINE", "easyocr"),
        ("STORAGE_BACKEND", "gcs"),
        ("APP_ENV", "staging"),
        ("LLM_PROVIDER", "not a provider"),
        ("LOG_LEVEL", "verbose"),
    ],
)
def test_unknown_choice_is_rejected(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        load()


def test_log_level_is_case_insensitive(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert load().log_level == "DEBUG"


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MAX_UPLOAD_SIZE_MB", "0"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_MAX_RETRIES", "6"),
        ("LIBREOFFICE_TIMEOUT_SECONDS", "0"),
    ],
)
def test_numeric_bounds_are_enforced(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        load()


def test_llm_base_url_must_be_a_url(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.internal.example:8443/v1")
    assert load().llm_base_url is not None

    monkeypatch.setenv("LLM_BASE_URL", "not a url")
    with pytest.raises(ValidationError):
        load()


# ----------------------------------------------------------------------------------- CORS


def test_cors_origins_are_split_and_deduplicated(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000, http://localhost:8501 ,http://localhost:3000",
    )

    assert load().cors_allowed_origins == ["http://localhost:3000", "http://localhost:8501"]


@pytest.mark.parametrize("origin", ["localhost:3000", "http://localhost:3000/", "ftp://host"])
def test_invalid_cors_origin_is_rejected(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origin)

    with pytest.raises(ValidationError):
        load()


def test_wildcard_cors_is_only_allowed_outside_production(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    assert load().cors_allowed_origins == ["*"]

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValidationError) as exc_info:
        load()
    assert "production" in str(exc_info.value)


# ------------------------------------------------------------------------------ extensions


def test_extensions_are_normalised(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_TEMPLATE_EXTENSIONS", ".DOCX, pdf , pdf")
    monkeypatch.setenv("ALLOWED_EVENT_FILE_EXTENSIONS", ".XLSX,.CSV")

    settings = load()

    assert settings.allowed_template_extensions == ["docx", "pdf"]
    assert settings.allowed_event_file_extensions == ["xlsx", "csv"]


def test_template_extensions_are_limited_to_supported_formats(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_TEMPLATE_EXTENSIONS", "docx,txt")

    with pytest.raises(ValidationError) as exc_info:
        load()

    assert "txt" in str(exc_info.value)


@pytest.mark.parametrize("value", ["docx;exe", "../pdf", "do cx"])
def test_extensions_with_unsafe_characters_are_rejected(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ALLOWED_EVENT_FILE_EXTENSIONS", value)

    with pytest.raises(ValidationError):
        load()


# ------------------------------------------------------------------------------- storage


def test_s3_backend_requires_all_s3_settings(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "reports")

    with pytest.raises(ValidationError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "S3_ENDPOINT_URL" in message
    assert "S3_ACCESS_KEY_ID" in message
    assert "S3_SECRET_ACCESS_KEY" in message
    assert "S3_BUCKET" not in message


def test_s3_backend_loads_when_fully_configured(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.com")
    monkeypatch.setenv("S3_BUCKET", "reports")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access-key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret-key")

    settings = load()

    assert settings.storage_backend == "s3"
    assert settings.s3_bucket == "reports"
    assert "secret-key" not in repr(settings)


# --------------------------------------------------------------------------- .env handling


def test_values_are_loaded_from_an_env_file(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in required_env:
        monkeypatch.delenv(name)
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "\n".join(f"{name}={value}" for name, value in required_env.items())
        + "\nLOG_LEVEL=warning\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.log_level == "WARNING"
    assert settings.llm_model == "test-model"


def test_env_example_lists_exactly_the_settings_fields() -> None:
    documented = set(read_env_example())
    declared = {name.upper() for name in Settings.model_fields}

    assert documented == declared


def test_env_example_contains_no_secret_values() -> None:
    values = read_env_example()

    for variable in SECRET_VARIABLES:
        assert values[variable] == "", f"{variable} must be empty in .env.example"


def test_env_example_is_a_valid_configuration_once_required_values_are_filled(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in required_env:
        monkeypatch.delenv(name)
    values = read_env_example()
    values.update(required_env)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.cors_allowed_origins == []
    assert settings.max_upload_size_mb == 25


# ------------------------------------------------------------------------- get_settings


def test_get_settings_is_cached_until_cleared(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    first = get_settings()

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert get_settings() is first
    assert get_settings().log_level == "INFO"

    get_settings.cache_clear()
    assert get_settings().log_level == "DEBUG"


def test_get_settings_reports_every_missing_variable() -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings()

    reported = {problem["variable"] for problem in exc_info.value.details["problems"]}
    assert reported == set(REQUIRED_VARIABLES)
    assert exc_info.value.code == "configuration_error"


def test_get_settings_error_does_not_leak_secret_values(
    required_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://admin:supersecret@db.example/app")

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings()

    error = exc_info.value
    assert "DATABASE_URL" in error.message
    assert "supersecret" not in error.message
    assert "supersecret" not in repr(error.details)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
