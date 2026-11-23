from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql://report_user:test-password@localhost:5432/report_generator_test",
    "LLM_PROVIDER": "openai",
    "LLM_MODEL": "test-model",
    "LLM_API_KEY": "test-llm-key",
    "EMBEDDING_MODEL": "test-embedding-model",
    "OCR_ENGINE": "tesseract",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Every test starts with no configuration variables and no .env file in the cwd."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set the minimum valid configuration and return it."""
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    return dict(REQUIRED_ENV)
