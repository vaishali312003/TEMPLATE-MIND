import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import PurePosixPath

import pytest

from app.core.config import Settings
from app.core.logging import (
    configure_logging,
    generate_request_id,
    get_request_id,
    reset_request_id,
    set_request_id,
)

SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_servers = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in SERVER_LOGGERS
    }
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)
    for name, (handlers, propagate) in saved_servers.items():
        server_logger = logging.getLogger(name)
        server_logger.handlers[:] = handlers
        server_logger.propagate = propagate


def make_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_production_logs_one_json_object_per_line(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(make_settings(monkeypatch, APP_ENV="production"))
    logger = logging.getLogger("tests.sample")

    token = set_request_id("abc123")
    try:
        logger.info(
            "report generated",
            extra={"report_id": 42, "path": PurePosixPath("reports/output.docx")},
        )
    finally:
        reset_request_id(token)

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.sample"
    assert payload["message"] == "report generated"
    assert payload["request_id"] == "abc123"
    assert payload["context"] == {"report_id": 42, "path": "reports/output.docx"}
    assert payload["timestamp"].endswith("+00:00")


def test_json_log_includes_exception_details(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(make_settings(monkeypatch, APP_ENV="production"))
    logger = logging.getLogger("tests.sample")

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("step failed")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["message"] == "step failed"
    assert "ValueError: boom" in payload["exception"]
    assert payload["request_id"] is None


def test_secrets_passed_as_context_stay_masked(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = make_settings(monkeypatch, APP_ENV="production")
    configure_logging(settings)

    logging.getLogger("tests.sample").info("configured", extra={"key": settings.llm_api_key})

    output = capsys.readouterr().out
    assert "test-llm-key" not in output
    assert "**********" in output


def test_development_uses_readable_console_format(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(make_settings(monkeypatch, APP_ENV="development"))

    token = set_request_id("req-1")
    try:
        logging.getLogger("tests.sample").warning("low disk")
    finally:
        reset_request_id(token)

    line = capsys.readouterr().out.strip()
    assert "WARNING" in line
    assert "[req-1]" in line
    assert "tests.sample: low disk" in line
    assert not line.startswith("{")


def test_console_format_shows_placeholder_without_request(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(make_settings(monkeypatch))

    logging.getLogger("tests.sample").warning("startup")

    assert "[-]" in capsys.readouterr().out


def test_log_level_filters_records(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(make_settings(monkeypatch, LOG_LEVEL="WARNING"))
    logger = logging.getLogger("tests.sample")

    logger.info("hidden")
    logger.warning("shown")

    output = capsys.readouterr().out
    assert "hidden" not in output
    assert "shown" in output


def test_configure_logging_is_idempotent(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = make_settings(monkeypatch)
    configure_logging(settings)
    configure_logging(settings)

    logging.getLogger("tests.sample").warning("once")

    assert len(logging.getLogger().handlers) == 1
    assert capsys.readouterr().out.count("once") == 1


def test_server_loggers_are_routed_through_the_root_handler(
    required_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.NullHandler())
    access.propagate = False

    configure_logging(make_settings(monkeypatch))
    access.warning("GET /health 200")

    assert access.handlers == []
    assert access.propagate is True
    assert "GET /health 200" in capsys.readouterr().out


def test_request_id_defaults_to_none_and_can_be_reset() -> None:
    assert get_request_id() is None

    token = set_request_id("abc")
    assert get_request_id() == "abc"

    reset_request_id(token)
    assert get_request_id() is None


def test_request_id_is_isolated_between_concurrent_tasks() -> None:
    async def handle(request_id: str) -> str | None:
        token = set_request_id(request_id)
        await asyncio.sleep(0)
        seen = get_request_id()
        reset_request_id(token)
        return seen

    async def main() -> list[str | None]:
        return list(await asyncio.gather(handle("a"), handle("b")))

    assert asyncio.run(main()) == ["a", "b"]
    assert get_request_id() is None


def test_generated_request_ids_are_unique_hex_strings() -> None:
    first, second = generate_request_id(), generate_request_id()

    assert first != second
    assert len(first) == 32
    int(first, 16)
